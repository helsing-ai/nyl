"""Service for template evaluation and inline resource generation."""

from concurrent.futures import Future, ThreadPoolExecutor

from nyl.generator import reconcile_generator
from nyl.generator.dispatch import DispatchingGenerator
from nyl.resources.postprocessor import PostProcessor
from nyl.services.manifest import ManifestsWithSource
from nyl.services.namespace import NamespaceResolverService
from nyl.templating import NylTemplateEngine
from nyl.tools.types import Resource, ResourceList


class TemplatingService:
    """Service for evaluating templates and generating inline resources.

    This service orchestrates the template engine evaluation and optionally
    handles inline resource generation with parallelization support.
    """

    def __init__(
        self,
        template_engine: NylTemplateEngine,
        generator: DispatchingGenerator,
        namespace_resolver: NamespaceResolverService,
    ):
        """Create a TemplatingService.

        Args:
            template_engine: The template engine for evaluating resources
            generator: The generator for creating inline resources
            namespace_resolver: Service for resolving namespaces
        """
        self.template_engine = template_engine
        self.generator = generator
        self.namespace_resolver = namespace_resolver

    def evaluate_template(
        self,
        source: ManifestsWithSource,
        default_namespace: str,
        inline: bool = True,
        jobs: int | None = None,
    ) -> tuple[ResourceList, list[PostProcessor]]:
        """Evaluate templates in a manifest source.

        This performs:
        1. Template evaluation on all resources
        2. Optional inline resource generation (with parallelization)
        3. Extraction of post-processors

        Args:
            source: The manifest source to evaluate (modified in-place)
            default_namespace: Default namespace for generated resources
            inline: Whether to inline generated resources
            jobs: Number of parallel jobs for inline generation (None = auto)

        Returns:
            Tuple of (processed resources, extracted post-processors)
        """
        # First pass: evaluate templates on all resources
        source.resources = self.template_engine.evaluate(source.resources)

        # Second pass: handle inline resource generation if requested
        if inline:
            source.resources = self._generate_inline_resources(
                source.resources,
                default_namespace,
                jobs,
            )

        # Extract post-processors from the resource list
        processed_resources, post_processors = PostProcessor.extract_from_list(source.resources)
        source.resources = processed_resources

        return source.resources, post_processors

    def _generate_inline_resources(
        self,
        resources: ResourceList,
        default_namespace: str,
        jobs: int | None,
    ) -> ResourceList:
        """Generate inline resources with parallel processing.

        Args:
            resources: The resources to process
            default_namespace: Default namespace for generated resources
            jobs: Number of parallel workers (None = auto)

        Returns:
            Resources with inline resources generated and expanded
        """
        with ThreadPoolExecutor(max_workers=jobs) as executor:

            def new_generation(resource: Resource) -> Future[ResourceList]:
                """Create a future for generating inline resources from a resource."""

                def worker() -> ResourceList:
                    # Evaluate the resource in isolation
                    resources_ = self.template_engine.evaluate(ResourceList([resource]))
                    # Ensure generated resources have the default namespace
                    self.namespace_resolver.populate_namespaces(resources_, default_namespace)
                    return resources_

                return executor.submit(worker)

            # Reconcile generators, skipping PostProcessor resources
            return reconcile_generator(
                self.generator,
                resources,
                new_generation_callback=new_generation,
                skip_resources=[PostProcessor],
            )
