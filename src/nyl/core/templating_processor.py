from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, cast, List, Tuple # Added List and Tuple

from loguru import logger

from kubernetes.client.api_client import ApiClient
from nyl.generator.dispatch import DispatchingGenerator
from nyl.generator import reconcile_generator
from nyl.profiles import ProfileManager
from nyl.project.config import ProjectConfig
from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.resources.applyset import APPLYSET_LABEL_PART_OF, ApplySet
from nyl.resources.postprocessor import PostProcessor
from nyl.secrets.config import SecretsConfig
from nyl.templating import NylTemplateEngine
from nyl.tools import yaml
from nyl.tools.kubernetes import drop_empty_metadata_labels, populate_namespace_to_resources
from nyl.tools.types import Resource, ResourceList

DEFAULT_NAMESPACE_ANNOTATION = "nyl.io/is-default-namespace"


class OnLookupFailure(str, Enum):
    """
    Defines the behavior when a `lookup()` call fails during template rendering.
    """
    Error = "Error"
    CreatePlaceholder = "CreatePlaceholder"
    SkipResource = "SkipResource"

    def to_literal(self) -> Literal["Error", "CreatePlaceholder", "SkipResource"]:
        return cast(Any, self.name)  # type: ignore[no-any-return]


@dataclass
class ManifestsWithSource:
    """
    Represents a list of Kubernetes resources loaded from a particular source manifest file.
    """

    resources: ResourceList
    file: Path


def load_manifests(paths: list[Path]) -> list[ManifestsWithSource]:
    """
    Loads all Kubernetes resources from a list of files or directories.

    If a path in the list is a directory, it will search for `.yaml` files
    within that directory (non-recursively). Files starting with `nyl-`, `.`,
    or `_` are ignored.

    Args:
        paths: A list of `pathlib.Path` objects, where each path can be
               a YAML file or a directory containing YAML files.

    Returns:
        A list of `ManifestsWithSource` objects, each containing the resources
        from one source file and the path to that file.
    """
    logger.trace("Loading manifests from paths: {}", paths)

    files = []
    for path_item in paths:  # path is a reserved keyword
        if path_item.is_dir():
            for item in path_item.iterdir():
                if (
                    item.name.startswith("nyl-")
                    or item.name.startswith(".")
                    or item.name.startswith("_")
                    or item.suffix != ".yaml"
                    or not item.is_file()
                ):
                    continue
                files.append(item)
        else:
            files.append(path_item)

    logger.trace("Files to load: {}", files)
    if len(files) == 0:
        logger.warning(
            "No valid manifests found in the paths. Nyl does not recursively enumerate directory contents, make sure "
            "you are specifying at least one path with valid YAML manifests to render.",
            paths,
        )

    result = []
    for file_path in files:
        resources = ResourceList(list(map(Resource, filter(None, yaml.loads_all(file_path.read_text())))))
        result.append(ManifestsWithSource(resources, file_path))

    return result


def is_namespace_resource(resource: Resource) -> bool:
    """
    Check if a resource is a namespace resource.
    """

    return resource.get("apiVersion") == "v1" and resource.get("kind") == "Namespace"


def get_default_namespace_for_manifest(source: ManifestsWithSource, fallback: str | None = None) -> str:
    """
    Given the contents of a manifest file, determine the fallback namespace to apply to resources that have been
    recorded without a namespace.

    Usually, in Kubernetes, when a namespaced resource has no `metadata.namespace` field, it is assumed that its
    namespace is `"default"`. However, in Nyl we take various hints to fill in a more appropriate namespace for the
    resource given the context in which it was recorded:

    - If there is no `v1/Namespace` resource declared in the manifest, the *fallback* namespace is used, and if not
    set, the name of the manifest file (without the extension, which may be `.yml`, `.yaml` or `.nyl.yaml`).

    - If there is exactly one `v1/Namespace` resource declared in the manifest, that namespace's name is used as the
    fallback.

    - If there are multiple `v1/Namespace` resources declared in the manifest, we pick the one with the
    `nyl.io/is-default-namespace` label. If there is no such namespace, a warning is logged and we pick the first one
    alphabetically.

    Returns:
        The name of the default namespace to resources in the given manifest source file.
    """

    namespace_resources = [x for x in source.resources if is_namespace_resource(x)]

    if len(namespace_resources) == 0:
        if fallback is not None:
            return fallback
        use_namespace = source.file.stem
        if use_namespace.endswith(".nyl"):
            use_namespace = use_namespace[:-4]
        logger.warning(
            "Manifest '{}' does not define a Namespace resource. Using '{}' as the default namespace.",
            source.file,
            use_namespace,
        )
        return use_namespace

    if len(namespace_resources) == 1:
        logger.debug(
            "Manifest '{}' defines exactly one Namespace resource. Using '{}' as the default namespace.",
            source.file,
            namespace_resources[0]["metadata"]["name"],
        )
        return namespace_resources[0]["metadata"]["name"] # type: ignore[no-any-return]

    default_namespaces = {
        x["metadata"]["name"]
        for x in namespace_resources
        if x["metadata"].get("annotations", {}).get(DEFAULT_NAMESPACE_ANNOTATION, "false") == "true"
    }

    if len(default_namespaces) == 0:
        use_namespace = sorted(x["metadata"]["name"] for x in namespace_resources)[0]
        logger.warning(
            "Manifest '{}' defines {} namespaces, but none of them have the `{}` label. Using the first one "
            "alphabetically ({}) as the default namespace.",
            source.file,
            len(namespace_resources),
            DEFAULT_NAMESPACE_ANNOTATION,
            use_namespace,
        )
        return use_namespace # type: ignore[no-any-return]

    if len(default_namespaces) > 1:
        # Replaced exit(1) with ValueError
        raise ValueError(
            f"Manifest '{source.file}' defines {len(namespace_resources)} namespaces, but more than one of them have "
            f"the `{DEFAULT_NAMESPACE_ANNOTATION}` label. The following namespaces have the label: "
            f"{', '.join(default_namespaces)}"
        )

    return default_namespaces.pop() # type: ignore[no-any-return]


def process_templates(
    paths: List[Path],
    project_config: ProjectConfig,
    secrets_config: SecretsConfig,
    profile_manager: ProfileManager,
    api_client: ApiClient,
    profile_name: Optional[str],
    secrets_provider_name: str,
    on_lookup_failure_config: Literal["Error", "CreatePlaceholder", "SkipResource"],
    default_namespace: Optional[str],
    inline_enabled: bool,
    jobs: Optional[int],
    cache_dir: Path,
    applyset_part_of: bool,
    current_working_dir: Path, # Added current_working_dir
    kube_version_env: Optional[str],
    kube_api_versions_env: Optional[str],
) -> List[Tuple[Path, ResourceList, Optional[ApplySet]]]:
    """
    Processes a list of template files, rendering them into Kubernetes resources.

    This function orchestrates the loading, templating, and processing of
    Kubernetes manifests. It handles Nyl-specific features like inlined resources,
    ApplySet generation, namespace population, and post-processing.

    Args:
        paths: A list of `pathlib.Path` objects pointing to YAML manifest files
               or directories containing them.
        project_config: The active `ProjectConfig` for the Nyl project.
        secrets_config: The `SecretsConfig` containing secrets provider details.
        profile_manager: The `ProfileManager` to access profile-specific values.
        api_client: A Kubernetes `ApiClient` for performing lookups.
        profile_name: The name of the Nyl profile to use for template values.
                      If `None`, the default profile is used if available.
        secrets_provider_name: The name of the secrets provider to use from
                               `secrets_config`.
        on_lookup_failure_config: Defines behavior for `lookup()` failures.
                                  Can be "Error", "CreatePlaceholder", or "SkipResource".
        default_namespace: An optional default namespace to apply to resources
                           that don't specify one.
        inline_enabled: If `True`, Nyl inlined resources (e.g., `nyl.io/v1/Template`)
                        will be evaluated.
        jobs: The number of parallel jobs to use for evaluating inlined
              resources. `None` means an adequate number is chosen automatically.
        cache_dir: The `pathlib.Path` to the directory for storing cache data.
        applyset_part_of: If `True`, adds the 'applyset.kubernetes.io/part-of'
                          label to resources belonging to an ApplySet.
        current_working_dir: The current working directory, used for resolving
                             relative paths in components.
        kube_version_env: Optional Kubernetes version string (e.g., "1.28") from env.
        kube_api_versions_env: Optional comma-separated string of API versions from env.

    Returns:
        A list of tuples. Each tuple contains:
        - `Path`: The path to the source manifest file.
        - `ResourceList`: The list of processed Kubernetes resources from that file.
        - `Optional[ApplySet]`: The ApplySet object associated with the resources,
                                 if one was generated or found.

    Raises:
        KeyError: If a specified `profile_name` or `secrets_provider_name`
                  is not found in the respective configurations.
        ValueError: For various configuration errors, such as multiple ApplySets
                    in a single file, or a resource missing a 'metadata' key.
        # Note: TemplateError from the templating engine itself might also propagate.
    """
    processed_results: List[Tuple[Path, ResourceList, Optional[ApplySet]]] = []

    generator = DispatchingGenerator.default(
        cache_dir=cache_dir,
        search_path=project_config.config.settings.search_path,
        components_path=project_config.get_components_path(),
        working_dir=current_working_dir, # Use current_working_dir
        client=api_client,
        kube_version=kube_version_env,
        kube_api_versions=kube_api_versions_env,
    )

    for source in load_manifests(paths):
        logger.opt(colors=True).info("Rendering manifests from <blue>{}</>.", source.file)

        template_engine = NylTemplateEngine(
            secrets_config.providers[secrets_provider_name],
            api_client,
            on_lookup_failure=on_lookup_failure_config,
        )

        # Seed the template engine with the profile values.
        # If no profile was specified via --profile or ARGOCD_ENV_NYL_PROFILE, we fall back to the default profile.
        # However, if the default profile does not exist, we don't want to raise an error, as this would be a
        # breaking change for users who upgrade Nyl without having a default profile defined.
        # If a profile *was* specified and it doesn't exist, we *do* want to raise an error.
        # profile_config = profile_manager.config.profiles.get(profile_name or DEFAULT_PROFILE) # DEFAULT_PROFILE is not available here
        active_profile_name = profile_name or profile_manager.get_default_profile_name() # Adapt to use profile_manager method
        if active_profile_name:
            profile_config = profile_manager.config.profiles.get(active_profile_name)
            if profile_config is not None:
                vars(template_engine.values).update(profile_config.values)
            elif profile_name is not None: # Only raise if a profile was explicitly requested
                raise KeyError(f"Profile '{profile_name}' not found in nyl-profiles.yaml")
        # else: No profile was requested, and the default profile doesn't exist. Do nothing.


        # Look for objects that contain local variables and feed them into the template engine.
        for resource in source.resources[:]:
            if "apiVersion" in resource or "kind" in resource:
                continue
            if not any(k.startswith("$") for k in resource.keys()):
                # Neither a Kubernetes object, nor one defining local variables. Hmm..
                continue
            if any(not k.startswith("$") for k in resource.keys()):
                # Can't have keys that don't start with `$` in a local variable object.
                # Replaced exit(1) with ValueError
                raise ValueError(
                    f"An object that looks like a local value definition in '{source.file}' has "
                    f"keys that don't start with `$`, which is not allowed in this context.\n\n{yaml.dumps(resource)}"
                )
            for key, value in resource.items():
                assert key.startswith("$"), key
                setattr(template_engine.values, key[1:], value)
            source.resources.remove(resource)

        # Begin populating the default namespace to resources.
        current_default_namespace = get_default_namespace_for_manifest(source, default_namespace)
        populate_namespace_to_resources(source.resources, current_default_namespace)

        source.resources = template_engine.evaluate(source.resources)
        if inline_enabled:
            # Need to import Future from concurrent.futures
            from concurrent.futures import Future, ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=jobs) as executor:

                def new_generation(resource: Resource) -> Future[ResourceList]:
                    def worker() -> ResourceList:
                        resources_ = template_engine.evaluate(ResourceList([resource]))
                        populate_namespace_to_resources(resources_, current_default_namespace)
                        return resources_

                    return executor.submit(worker)

                source.resources = reconcile_generator(
                    generator,
                    source.resources,
                    new_generation_callback=new_generation,
                    skip_resources=[PostProcessor],
                )

        source.resources, post_processors = PostProcessor.extract_from_list(source.resources)

        # Find the namespaces that are defined in the file. If we find any resources without a namespace, we will
        # inject that namespace name into them. Also find the applyset defined in the file.
        # namespaces: set[str] = set() # Not used
        applyset: Optional[ApplySet] = None # Ensure applyset is always defined

        for resource_item in list(source.resources): # Renamed resource to resource_item to avoid conflict
            if is_namespace_resource(resource_item):
                # namespaces.add(resource_item["metadata"]["name"]) # Not used
                pass
            elif ApplySet.matches(resource_item):
                if applyset is not None:
                    # Replaced exit(1) with ValueError
                    raise ValueError(
                        f"Multiple ApplySet resources defined in '{source.file}', there can only be one per source."
                    )
                applyset = ApplySet.load(resource_item)
                source.resources.remove(resource_item)

        if not applyset and project_config.config.settings.generate_applysets:
            if not current_default_namespace:
                # Replaced exit(1) with ValueError
                raise ValueError(
                    f"No default namespace defined for '{source.file}', but it is required for the automatically "
                    f"generated nyl.io/v1/ApplySet resource (the ApplySet is named after the default namespace)."
                )

            applyset_name = current_default_namespace
            applyset = ApplySet.new(applyset_name)
            logger.opt(colors=True).info(
                "Automatically creating ApplySet for <blue>{}</> (name: <magenta>{}</>).", source.file, applyset_name
            )

        if applyset is not None:
            applyset.set_group_kinds(source.resources)
            # HACK: Kubectl 1.30 can't create the custom resource, so we need to create it. But it will also reject
            #       using the custom resource unless it has the tooling label set appropriately. For more details, see
            #       https://github.com/helsing-ai/nyl/issues/5.
            if generator.kube_version: # Add check for kube_version presence
                applyset.tooling = f"kubectl/v{generator.kube_version}"
            applyset.validate()

        # Validate resources.
        for resource in source.resources:
            # Inline resources often don't have metadata and they are not persisted to the cluster, hence
            # we don't need to process them here.
            if NylResource.matches(resource, API_VERSION_INLINE):
                assert not inline_enabled, "Inline resources should have been processed by this time." # Use inline_enabled
                continue

            if "metadata" not in resource:
                 # Replaced exit(1) with ValueError
                raise ValueError(
                    f"A resource in '{source.file}' has no 'metadata' key:\n\n{yaml.dump(resource, indent=2)}"
                )


        # Tag resources as part of the current apply set, if any.
        if applyset is not None and applyset_part_of:
            for resource in source.resources:
                if APPLYSET_LABEL_PART_OF not in (labels := resource["metadata"].setdefault("labels", {})):
                    labels[APPLYSET_LABEL_PART_OF] = applyset.id

        populate_namespace_to_resources(source.resources, current_default_namespace)
        drop_empty_metadata_labels(source.resources)

        # Now apply the post-processor.
        source.resources = PostProcessor.apply_all(source.resources, post_processors, source.file)
        
        processed_results.append((source.file, source.resources, applyset))

    return processed_results
