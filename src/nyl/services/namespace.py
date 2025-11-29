"""Service for resolving and managing Kubernetes namespaces in manifests."""

from typing import cast

from loguru import logger

from nyl.models.errors import NamespaceAmbiguityError
from nyl.services.manifest import ManifestsWithSource
from nyl.tools.kubernetes import populate_namespace_to_resources
from nyl.tools.types import Resource, ResourceList

DEFAULT_NAMESPACE_ANNOTATION = "nyl.io/is-default-namespace"


class NamespaceResolverService:
    """Service for resolving default namespaces for Kubernetes manifests.

    This service implements Nyl's namespace resolution strategy:
    - If no Namespace resource exists, use fallback or filename
    - If exactly one Namespace resource exists, use its name
    - If multiple Namespace resources exist, use the one with the annotation
    - Raise error if multiple namespaces and no annotation
    """

    def resolve_default_namespace(self, source: ManifestsWithSource, fallback: str | None = None) -> str:
        """Determine the default namespace for a manifest file.

        Args:
            source: The manifest source to resolve namespace for
            fallback: Optional fallback namespace to use if no Namespace resources exist

        Returns:
            The default namespace name

        Raises:
            NamespaceAmbiguityError: If multiple Namespace resources exist with no clear default
        """
        namespace_resources = self.find_namespace_resources(source.resources)

        # Case 1: No namespace resources
        if len(namespace_resources) == 0:
            if fallback is not None:
                return fallback

            # Derive from filename
            use_namespace = source.file.stem
            if use_namespace.endswith(".nyl"):
                use_namespace = use_namespace[:-4]

            logger.warning(
                "Manifest '{}' does not define a Namespace resource. Using '{}' as the default namespace.",
                source.file,
                use_namespace,
            )
            return use_namespace

        # Case 2: Exactly one namespace resource
        if len(namespace_resources) == 1:
            namespace_name = cast(str, namespace_resources[0]["metadata"]["name"])
            logger.debug(
                "Manifest '{}' defines exactly one Namespace resource. Using '{}' as the default namespace.",
                source.file,
                namespace_name,
            )
            return namespace_name

        # Case 3: Multiple namespace resources - need to find the default
        default_namespaces = {
            cast(str, ns["metadata"]["name"])
            for ns in namespace_resources
            if ns["metadata"].get("annotations", {}).get(DEFAULT_NAMESPACE_ANNOTATION, "false") == "true"
        }

        # No namespace marked as default - use alphabetically first with warning
        if len(default_namespaces) == 0:
            namespace_names = sorted(cast(str, ns["metadata"]["name"]) for ns in namespace_resources)
            use_namespace = namespace_names[0]

            logger.warning(
                "Manifest '{}' defines {} namespaces, but none of them have the '{}' annotation. "
                "Using the first one alphabetically ({}) as the default namespace.",
                source.file,
                len(namespace_resources),
                DEFAULT_NAMESPACE_ANNOTATION,
                use_namespace,
            )
            return use_namespace

        # Multiple namespaces marked as default - error
        if len(default_namespaces) > 1:
            raise NamespaceAmbiguityError(
                f"Multiple Namespace resources in {source.file} have the '{DEFAULT_NAMESPACE_ANNOTATION}' annotation",
                namespaces=list(default_namespaces),
                file_path=str(source.file),
                hint=f"Only one Namespace should have the '{DEFAULT_NAMESPACE_ANNOTATION}: \"true\"' annotation. "
                "Remove the annotation from all but one namespace.",
            )

        # Exactly one default namespace found
        return cast(str, default_namespaces.pop())

    def populate_namespaces(self, resources: ResourceList, namespace: str) -> None:
        """Populate the default namespace to resources that don't have one.

        This delegates to the existing populate_namespace_to_resources function
        from the tools module, providing a cleaner service interface.

        Args:
            resources: The resource list to populate namespaces in (modified in-place)
            namespace: The default namespace to use
        """
        populate_namespace_to_resources(resources, namespace)

    def find_namespace_resources(self, resources: ResourceList) -> list[Resource]:
        """Find all Namespace resources in a resource list.

        Args:
            resources: The resource list to search

        Returns:
            List of Namespace resources
        """
        return [r for r in resources if self._is_namespace_resource(r)]

    def _is_namespace_resource(self, resource: Resource) -> bool:
        """Check if a resource is a v1/Namespace resource.

        Args:
            resource: The resource to check

        Returns:
            True if the resource is a Namespace
        """
        return resource.get("apiVersion") == "v1" and resource.get("kind") == "Namespace"
