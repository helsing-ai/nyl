import atexit
import json
import os
import time
from enum import Enum
from pathlib import Path
from textwrap import indent
from typing import Any, Literal, Optional, cast

from kubernetes.client.api_client import ApiClient
from loguru import logger
from typer import Argument, Option

from nyl.commands import app
from nyl.core import DIContainer, setup_base_container, setup_service_container
from nyl.generator.dispatch import DispatchingGenerator
from nyl.models.context import TemplateContext
from nyl.profiles import DEFAULT_PROFILE, ProfileManager
from nyl.project.config import ProjectConfig
from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.resources.postprocessor import PostProcessor
from nyl.secrets.config import SecretsConfig
from nyl.services.kubernetes_apply import KubernetesApplyService
from nyl.services.manifest import ManifestLoaderService
from nyl.services.namespace import NamespaceResolverService
from nyl.services.templating import TemplatingService
from nyl.templating import NylTemplateEngine
from nyl.tools import yaml
from nyl.tools.kubectl import Kubectl
from nyl.tools.kubernetes import drop_empty_metadata_labels
from nyl.tools.logging import lazy_str
from nyl.tools.types import Resource

DEFAULT_NAMESPACE_ANNOTATION = "nyl.io/is-default-namespace"


# Need an enum for typer
class OnLookupFailure(str, Enum):
    Error = "Error"
    CreatePlaceholder = "CreatePlaceholder"
    SkipResource = "SkipResource"

    def to_literal(self) -> Literal["Error", "CreatePlaceholder", "SkipResource"]:
        return cast(Any, self.name)  # type: ignore[no-any-return]


@app.command()
def template(
    paths: list[Path] = Argument(
        ..., help="The YAML file(s) to render. Can be a directory."
    ),
    profile: Optional[str] = Option(
        None, envvar="NYL_PROFILE", help="The Nyl profile to use."
    ),
    secrets_provider: str = Option(
        "default",
        "--secrets",
        envvar="NYL_SECRETS",
        help="The secrets provider to use.",
    ),
    in_cluster: bool = Option(
        False,
        help="Use the in-cluster Kubernetes configuration. The --profile option is ignored.",
    ),
    apply: bool = Option(
        False,
        help="Run `kubectl apply` on the rendered manifests, once for each source file. "
        "Implies `--no-applyset-part-of`. When an ApplySet is defined in the source file, it will be applied "
        "separately. Note that this option implies `kubectl --prune`.",
    ),
    diff: bool = Option(
        False,
        help="Run `kubectl diff` on the rendered manifests, once for each source file. Cannot be combined with "
        "`--apply`. Note that this does not generally ",
    ),
    generate_applysets: Optional[bool] = Option(
        None,
        help="Override the `generate_applysets` setting from the project configuration.",
    ),
    applyset_part_of: bool = Option(
        True,
        help="Add the 'applyset.kubernetes.io/part-of' label to all resources belonging to an ApplySet (if declared). "
        "This option must be disabled when passing the generated manifests to `kubectl apply --applyset=...`, as it "
        "would otherwise cause an error due to the label being present on the input data.",
    ),
    default_namespace: Optional[str] = Option(
        None,
        help="The name of the Kubernetes namespace to fill in to Kubernetes resource that don't have a namespace set. "
        "If this is not specified as an argument or via environment variables, it will default to the stem of the "
        "manifest source filename. Note that if a manifest defines a Namespace resource, that namespace is used "
        "instead, regardless of the value of this option. If a manifest source file defines multiple namespaces and a "
        "resource without namespace is encountered, this option is considered if it matches one of the namespaces "
        "defined in the file. Note that this option is usually problematic when rendering multiple files, as often "
        "a single file is intended to deploy into a single namespace.\n\n"
        "Note that Nyl's detection for cluster-scoped vs. namespace-scoped resources is not very good, yet.",
        envvar="ARGOCD_APP_NAMESPACE",
    ),
    inline: bool = Option(True, help="Evaluate Nyl inlined resources."),
    jobs: int | None = Option(
        None,
        "-j",
        "--jobs",
        help="The number of jobs to use for evaluating Nyl inlined resources. If not set, an adequate number of jobs is chosen automatically.",
        envvar="NYL_TEMPLATE_JOBS",
    ),
    state_dir: Optional[Path] = Option(
        None,
        help="The directory to store state in (such as kubeconfig files).",
        envvar="NYL_STATE_DIR",
    ),
    cache_dir: Optional[Path] = Option(
        None,
        help="The directory to store cache data in. If not set, a directory in the --state-dir is used.",
        envvar="NYL_CACHE_DIR",
    ),
    on_lookup_failure: OnLookupFailure | None = Option(
        None,
        help="Specify what to do when a lookup() call in a Nyl templated manifest fails. This overrides the nyl-project.toml setting if specified.",
    ),
) -> None:
    """
    Render a package template into full Kubernetes resources.
    """

    start_time = time.perf_counter()

    connect_with_profile = True
    if not profile and "ARGOCD_ENV_NYL_PROFILE" in os.environ:
        profile = os.environ["ARGOCD_ENV_NYL_PROFILE"]
        connect_with_profile = False

    if (
        paths == [Path(".")]
        and (env_paths := os.getenv("ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT")) is not None
    ):
        paths = [Path(p) for p in env_paths.split(",")]
        if not paths:
            logger.error(
                "<cyan>ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT</> is set, but empty."
            )
            exit(1)
        logger.opt(colors=True).info(
            "Using paths from <cyan>ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT</>: <blue>{}</>",
            lazy_str(lambda: ", ".join(map(str, paths))),
        )
    elif "ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT" in os.environ:
        logger.error(
            "<cyan>ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT</> is set, but paths were also provided via the command-line."
        )
        exit(1)

    if apply:
        # When running with --apply, we must ensure that the --applyset-part-of option is disabled, as it would cause
        # an error when passing the generated manifests to `kubectl apply --applyset=...`.
        applyset_part_of = False

    if apply and diff:
        logger.error("The --apply and --diff options cannot be combined.")
        exit(1)

    # Create DI container for this command execution
    container = DIContainer()

    # Setup base dependencies (ProfileManager, ProjectConfig, SecretsConfig, ApiClient)
    setup_base_container(
        container,
        in_cluster=in_cluster,
        profile=profile if connect_with_profile else None,
    )

    # Resolve dependencies from container
    client = container.resolve(ApiClient)
    project = container.resolve(ProjectConfig)
    secrets = container.resolve(SecretsConfig)

    if generate_applysets is not None:
        project.config.settings.generate_applysets = generate_applysets

    if state_dir is None:
        state_dir = project.file.parent / ".nyl" if project.file else Path(".nyl")

    if cache_dir is None:
        cache_dir = state_dir / "cache"

    kubectl = Kubectl()
    kubectl.env["KUBECTL_APPLYSET"] = "true"
    atexit.register(kubectl.cleanup)

    generator = DispatchingGenerator.default(
        cache_dir=cache_dir,
        search_path=project.config.settings.search_path,
        components_path=project.get_components_path(),
        working_dir=Path.cwd(),
        client=client,
        kube_version=os.getenv("KUBE_VERSION"),
        kube_api_versions=os.getenv("KUBE_API_VERSIONS"),
    )

    # Register command-specific dependencies in the container
    container.register_singleton(DispatchingGenerator, generator)
    container.register_singleton(Kubectl, kubectl)

    # Setup service layer
    setup_service_container(container, kubectl=kubectl)

    # Determine execution mode from apply/diff flags
    mode: Literal["apply", "diff"] | None = "apply" if apply else ("diff" if diff else None)

    # Create template context to encapsulate command execution state
    context = TemplateContext(
        container=container,
        project_config=project,
        working_dir=Path.cwd(),
        profile_name=profile,
        secrets_provider_name=secrets_provider,
        state_dir=state_dir,
        cache_dir=cache_dir,
        inline=inline,
        jobs=jobs,
        default_namespace=default_namespace,
        mode=mode,
        prune=False,  # Will be set per-source based on applyset
    )

    # Resolve services from context container
    manifest_loader = context.container.resolve(ManifestLoaderService)
    namespace_resolver = context.container.resolve(NamespaceResolverService)
    k8s_apply = context.container.resolve(KubernetesApplyService)

    for source in manifest_loader.load_manifests(paths):
        logger.opt(colors=True).info(
            "Rendering manifests from <blue>{}</>.", source.file
        )

        template_engine = NylTemplateEngine(
            secrets.providers[secrets_provider],
            client,
            on_lookup_failure=on_lookup_failure.to_literal()
            if on_lookup_failure
            else project.config.settings.on_lookup_failure,
        )

        # Seed the template engine with the profile values.
        # If no profile was specified via --profile or ARGOCD_ENV_NYL_PROFILE, we fall back to the default profile.
        # However, if the default profile does not exist, we don't want to raise an error, as this would be a
        # breaking change for users who upgrade Nyl without having a default profile defined.
        # If a profile *was* specified and it doesn't exist, we *do* want to raise an error.
        profile_config = context.container.resolve(ProfileManager).config.profiles.get(profile or DEFAULT_PROFILE)
        if profile_config is not None:
            vars(template_engine.values).update(profile_config.values)
        elif profile is not None:
            # A profile was explicitly requested, but it doesn't exist. Raise the error.
            raise KeyError(f"Profile '{profile}' not found in nyl-profiles.yaml")
        # else: No profile was requested, and the default profile doesn't exist. Do nothing.

        # Extract local variables from manifest and feed them into the template engine
        local_vars = manifest_loader.extract_local_variables(source)
        for key, value in local_vars.items():
            setattr(template_engine.values, key, value)

        # Begin populating the default namespace to resources.
        current_default_namespace = namespace_resolver.resolve_default_namespace(
            source, default_namespace
        )
        namespace_resolver.populate_namespaces(
            source.resources, current_default_namespace
        )

        # Use TemplatingService to evaluate templates and generate inline resources
        templating_service = TemplatingService(
            template_engine=template_engine,
            generator=generator,
            namespace_resolver=namespace_resolver,
        )
        source.resources, post_processors = templating_service.evaluate_template(
            source,
            default_namespace=current_default_namespace,
            inline=inline,
            jobs=jobs,
        )

        # Find the namespaces that are defined in the file
        k8s_apply.find_namespace_resources(source.resources)

        # Find or create ApplySet
        applyset = k8s_apply.find_or_create_applyset(
            source,
            namespace=current_default_namespace,
            auto_generate=project.config.settings.generate_applysets,
        )

        if applyset is not None:
            k8s_apply.prepare_applyset(applyset, source.resources)

        # Validate resources.
        for resource in source.resources:
            # Inline resources often don't have metadata and they are not persisted to the cluster, hence
            # we don't need to process them here.
            if NylResource.matches(resource, API_VERSION_INLINE):
                assert not inline, (
                    "Inline resources should have been processed by this time."
                )
                continue

            if "metadata" not in resource:
                logger.opt(colors=True).error(
                    "A resource in <yellow>'{}'</> has no <cyan>metadata</> key:\n\n{}",
                    source.file,
                    indent(yaml.dumps(resource), "  "),
                )
                exit(1)

        # Tag resources as part of the current apply set, if any.
        if applyset is not None:
            k8s_apply.tag_resources_with_applyset(
                source.resources, applyset, applyset_part_of
            )

        namespace_resolver.populate_namespaces(
            source.resources, current_default_namespace
        )
        drop_empty_metadata_labels(source.resources)

        # Now apply the post-processor.
        source.resources = PostProcessor.apply_all(
            source.resources, post_processors, source.file
        )

        if apply:
            logger.info(
                "Kubectl-apply {} resource(s) from '{}'",
                len(source.resources),
                source.file,
            )
            k8s_apply.apply_with_applyset(
                source.resources,
                applyset,
                source_file=str(source.file),
                prune=True if applyset else False,
            )
        elif diff:
            logger.info(
                "Kubectl-diff {} resource(s) from '{}'",
                len(source.resources),
                source.file,
            )
            k8s_apply.diff_with_applyset(source.resources, applyset)
        else:
            # If we're not going to be applying the resources immediately via `kubectl`, we print them to stdout.
            k8s_apply.output_yaml(source.resources, applyset)

    logger.log(
        "METRIC",
        "{}",
        json.dumps(
            {
                "type": "metrics.nyl.io/v1/NylTemplate",
                "data": {
                    "duration_seconds": time.perf_counter() - start_time,
                    "inputs": [
                        str(
                            p.absolute().relative_to(project.file.parent)
                            if project.file
                            else p
                        )
                        for p in paths
                    ],
                    # See https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/
                    "argocd_app_name": os.getenv("ARGOCD_APP_NAME"),
                    "argocd_app_namespace": os.getenv("ARGOCD_APP_NAMESPACE"),
                    "argocd_app_project_name": os.getenv("ARGOCD_APP_PROJECT_NAME"),
                    "argocd_app_revision": os.getenv("ARGOCD_APP_REVISION"),
                    "argocd_app_source_path": os.getenv("ARGOCD_APP_SOURCE_PATH"),
                    "argocd_app_source_repo_url": os.getenv(
                        "ARGOCD_APP_SOURCE_REPO_URL"
                    ),
                },
            }
        ),
    )


def is_namespace_resource(resource: Resource) -> bool:
    """
    Check if a resource is a namespace resource.
    """

    return resource.get("apiVersion") == "v1" and resource.get("kind") == "Namespace"
