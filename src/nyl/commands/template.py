import atexit
from concurrent.futures import Future, ThreadPoolExecutor
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import indent
import time
from typing import Any, Literal, Optional, cast

from loguru import logger
from typer import Argument, Option

from kubernetes.client.api_client import ApiClient
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config
from nyl.commands import PROVIDER, ApiClientConfig, app
from nyl.generator import reconcile_generator
from nyl.generator.dispatch import DispatchingGenerator
from nyl.profiles import DEFAULT_PROFILE, ProfileManager
from nyl.project.config import ProjectConfig
from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.resources.applyset import APPLYSET_LABEL_PART_OF, ApplySet
from nyl.resources.postprocessor import PostProcessor
from nyl.secrets.config import SecretsConfig
from nyl.templating import NylTemplateEngine
from nyl.tools import yaml
from nyl.tools.kubectl import Kubectl
from nyl.tools.kubernetes import populate_namespace_to_resources
from nyl.tools.logging import lazy_str
from nyl.tools.types import Manifest, Manifests

DEFAULT_NAMESPACE_ANNOTATION = "nyl.io/is-default-namespace"


# Need an enum for typer
class OnLookupFailure(str, Enum):
    Error = "Error"
    CreatePlaceholder = "CreatePlaceholder"
    SkipResource = "SkipResource"

    def to_literal(self) -> Literal["Error", "CreatePlaceholder", "SkipResource"]:
        return cast(Any, self.name)  # type: ignore[no-any-return]


@dataclass
class ManifestsWithSource:
    """
    Represents a list of manifests loaded from a particular source file.
    """

    manifests: Manifests
    file: Path


def get_incluster_kubernetes_client() -> ApiClient:
    logger.info("Using in-cluster configuration.")
    load_incluster_config()
    return ApiClient()


def get_profile_kubernetes_client(profiles: ProfileManager, profile: str | None) -> ApiClient:
    """
    Create a Kubernetes :class:`ApiClient` from the selected *profile*.

    If no *profile* is specified, but the profile manager contains at least one profile, the *profile* argument will
    default to the value of :data:`DEFAULT_PROFILE` (which is `"default"`). Otherwise, if no profile is selected and
    none is configured, the standard Kubernetes config loading is used (i.e. try `KUBECONFIG` and then
    `~/.kube/config`).
    """

    with profiles:
        # If no profile to activate is specified, and there are no profiles defined, we're not activating a
        # a profile. It should be valid to use Nyl without a `nyl-profiles.yaml` file.
        if profile is not None or profiles.config.profiles:
            profile = profile or DEFAULT_PROFILE
            active = profiles.activate_profile(profile)
            load_kube_config(str(active.kubeconfig))
        else:
            logger.opt(colors=True).info(
                "No <yellow>nyl-profiles.yaml</> file found, using default kubeconfig and context."
            )
            load_kube_config()
    return ApiClient()


@app.command()
def template(
    paths: list[Path] = Argument(..., help="The YAML file(s) to render. Can be a directory."),
    profile: Optional[str] = Option(None, envvar="NYL_PROFILE", help="The Nyl profile to use."),
    secrets_provider: str = Option("default", "--secrets", envvar="NYL_SECRETS", help="The secrets provider to use."),
    in_cluster: bool = Option(
        False, help="Use the in-cluster Kubernetes configuration. The --profile option is ignored."
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
        None, help="The directory to store state in (such as kubeconfig files).", envvar="NYL_STATE_DIR"
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

    if paths == [Path(".")] and (env_paths := os.getenv("ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT")) is not None:
        paths = [Path(p) for p in env_paths.split(",")]
        if not paths:
            logger.error("<cyan>ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT</> is set, but empty.")
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

    kubectl = Kubectl()
    kubectl.env["KUBECTL_APPLYSET"] = "true"
    atexit.register(kubectl.cleanup)

    # TODO: Allow that no Kubernetes configuration is available. This is needed if you want to run Nyl as an ArgoCD
    #       plugin without granting it access to the Kubernetes API. Most relevant bits of information that Nyl requires
    #       about the cluster are passed via the environment variables.
    #       See https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/
    PROVIDER.set(
        ApiClientConfig, ApiClientConfig(in_cluster=in_cluster, profile=profile if connect_with_profile else None)
    )
    client = PROVIDER.get(ApiClient)

    project = PROVIDER.get(ProjectConfig)
    if generate_applysets is not None:
        project.config.settings.generate_applysets = generate_applysets

    if state_dir is None:
        state_dir = project.file.parent / ".nyl" if project.file else Path(".nyl")

    if cache_dir is None:
        cache_dir = state_dir / "cache"

    secrets = PROVIDER.get(SecretsConfig)

    generator = DispatchingGenerator.default(
        cache_dir=cache_dir,
        search_path=project.config.settings.search_path,
        components_path=project.get_components_path(),
        working_dir=Path.cwd(),
        client=client,
        kube_version=os.getenv("KUBE_VERSION"),
        kube_api_versions=os.getenv("KUBE_API_VERSIONS"),
    )

    for source in load_manifests(paths):
        logger.opt(colors=True).info("Rendering manifests from <blue>{}</>.", source.file)

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
        profile_config = PROVIDER.get(ProfileManager).config.profiles.get(profile or DEFAULT_PROFILE)
        if profile_config is not None:
            vars(template_engine.values).update(profile_config.values)
        elif profile is not None:
            # A profile was explicitly requested, but it doesn't exist. Raise the error.
            raise KeyError(f"Profile '{profile}' not found in nyl-profiles.yaml")
        # else: No profile was requested, and the default profile doesn't exist. Do nothing.

        # Look for objects that contain local variables and feed them into the template engine.
        for manifest in source.manifests[:]:
            if "apiVersion" in manifest or "kind" in manifest:
                continue
            if not any(k.startswith("$") for k in manifest.keys()):
                # Neither a Kubernetes object, nor one defining local variables. Hmm..
                continue
            if any(not k.startswith("$") for k in manifest.keys()):
                # Can't have keys that don't start with `$` in a local variable object.
                logger.opt(colors=True).error(
                    "A manifest in <yellow>'{}'</> has keys that don't start with `$`:\n\n{}",
                    source.file,
                    yaml.dumps(manifest),
                )
                exit(1)
            for key, value in manifest.items():
                assert key.startswith("$"), key
                setattr(template_engine.values, key[1:], value)
            source.manifests.remove(manifest)

        # Begin populating the default namespace to resources.
        current_default_namespace = get_default_namespace_for_manifest(source, default_namespace)
        populate_namespace_to_resources(source.manifests, current_default_namespace)

        source.manifests = template_engine.evaluate(source.manifests)
        if inline:
            # Many operations for evaluating Nyl inline resources involve invoking other programs, such as Helm
            # and Kyverno, and benefit from parallelization with similar operations instead of a fully sequential
            # evaluation.
            with ThreadPoolExecutor(max_workers=jobs) as executor:

                def new_generation(manifest: Manifest) -> Future[Manifests]:
                    # This callback is invoked by reconcile_generator() for each new generation of manifests generated
                    # from other manifests, allowing to process and evaluate Nyl's inline resources generated by another
                    # such resource (e.g. a HelmChart or component generating another HelmChart resource).

                    def worker() -> Manifests:
                        manifests = template_engine.evaluate(Manifests([manifest]))
                        populate_namespace_to_resources(manifests, current_default_namespace)
                        return manifests

                    return executor.submit(worker)

                source.manifests = reconcile_generator(
                    generator,
                    source.manifests,
                    new_generation_callback=new_generation,
                    skip_resources=[PostProcessor],
                )

        # Find any PostProcessor resources and apply them. We apply the post-processors only later however
        # because it might cause resources without a `namespace: default` field to get that set. We want to have
        # an opportunity to fill that in ourselves first.
        source.manifests, post_processors = PostProcessor.extract_from_list(source.manifests)

        # Find the namespaces that are defined in the file. If we find any manifests without a namespace, we will
        # inject that namespace name into them. Also find the applyset defined in the file.
        namespaces: set[str] = set()
        applyset: ApplySet | None = None

        for manifest in list(source.manifests):
            if is_namespace_resource(manifest):
                namespaces.add(manifest["metadata"]["name"])
            elif ApplySet.matches(manifest):
                if applyset is not None:
                    logger.opt(colors=True).error(
                        "Multiple ApplySet resources defined in <yellow>{}</>, there can only be one per source.",
                        source.file,
                    )
                    exit(1)
                applyset = ApplySet.load(manifest)
                source.manifests.remove(manifest)

        if not applyset and project.config.settings.generate_applysets:
            if not current_default_namespace:
                logger.opt(colors=True).error(
                    "No default namespace defined for <yellow>{}</>, but it is required for the automatically "
                    "generated nyl.io/v1/ApplySet resource (the ApplySet is named after the default namespace).",
                    source.file,
                )
                exit(1)

            applyset_name = current_default_namespace
            applyset = ApplySet.new(applyset_name)
            logger.opt(colors=True).info(
                "Automatically creating ApplySet for <blue>{}</> (name: <magenta>{}</>).", source.file, applyset_name
            )

        if applyset is not None:
            applyset.set_group_kinds(source.manifests)
            # HACK: Kubectl 1.30 can't create the custom resource, so we need to create it. But it will also reject
            #       using the custom resource unless it has the tooling label set appropriately. For more details, see
            #       https://github.com/helsing-ai/nyl/issues/5.
            applyset.tooling = f"kubectl/v{generator.kube_version}"
            applyset.validate()

            if apply:
                # We need to ensure that ApplySet parent object exists before invoking `kubectl apply --applyset=...`.
                logger.opt(colors=True).info(
                    "Kubectl-apply ApplySet resource <yellow>{}</> from <cyan>{}</>.",
                    applyset.reference,
                    source.file,
                )
                kubectl.apply(Manifests([applyset.dump()]), force_conflicts=True)
            elif diff:
                kubectl.diff(Manifests([applyset.dump()]))
            else:
                print("---")
                print(yaml.dumps(applyset.dump()))

        # Validate resources.
        for manifest in source.manifests:
            # Inline resources often don't have metadata and they are not persisted to the cluster, hence
            # we don't need to process them here.
            if NylResource.matches(manifest, API_VERSION_INLINE):
                assert not inline, "Inline resources should have been processed by this timepdm lint."
                continue

            if "metadata" not in manifest:
                logger.opt(colors=True).error(
                    "A manifest in <yellow>'{}'</> has no <cyan>metadata</> key:\n\n{}",
                    source.file,
                    indent(yaml.dumps(manifest), "  "),
                )
                exit(1)

        # Tag resources as part of the current apply set, if any.
        if applyset is not None and applyset_part_of:
            for manifest in source.manifests:
                if APPLYSET_LABEL_PART_OF not in (labels := manifest["metadata"].setdefault("labels", {})):
                    labels[APPLYSET_LABEL_PART_OF] = applyset.id

        populate_namespace_to_resources(source.manifests, current_default_namespace)

        # Now apply the post-processor.
        source.manifests = PostProcessor.apply_all(source.manifests, post_processors, source.file)

        if apply:
            logger.info("Kubectl-apply {} manifest(s) from '{}'", len(source.manifests), source.file)
            kubectl.apply(
                manifests=source.manifests,
                applyset=applyset.reference if applyset else None,
                prune=True if applyset else False,
                force_conflicts=True,
            )
        elif diff:
            logger.info("Kubectl-diff {} manifest(s) from '{}'", len(source.manifests), source.file)
            kubectl.diff(manifests=source.manifests, applyset=applyset)
        else:
            # If we're not going to be applying the manifests immediately via `kubectl`, we print them to stdout.
            for manifest in source.manifests:
                print("---")
                print(yaml.dumps(manifest))

    logger.log(
        "METRIC",
        "{}",
        json.dumps(
            {
                "type": "metrics.nyl.io/v1/NylTemplate",
                "data": {
                    "duration_seconds": time.perf_counter() - start_time,
                    "inputs": [
                        str(p.absolute().relative_to(project.file.parent) if project.file else p) for p in paths
                    ],
                    # See https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/
                    "argocd_app_name": os.getenv("ARGOCD_APP_NAME"),
                    "argocd_app_namespace": os.getenv("ARGOCD_APP_NAMESPACE"),
                    "argocd_app_project_name": os.getenv("ARGOCD_APP_PROJECT_NAME"),
                    "argocd_app_revision": os.getenv("ARGOCD_APP_REVISION"),
                    "argocd_app_source_path": os.getenv("ARGOCD_APP_SOURCE_PATH"),
                    "argocd_app_source_repo_url": os.getenv("ARGOCD_APP_SOURCE_REPO_URL"),
                },
            }
        ),
    )


def load_manifests(paths: list[Path]) -> list[ManifestsWithSource]:
    """
    Load all manifests from a directory.
    """

    logger.trace("Loading manifests from paths: {}", paths)

    files = []
    for path in paths:
        if path.is_dir():
            for item in path.iterdir():
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
            files.append(path)

    logger.trace("Files to load: {}", files)
    if len(files) == 0:
        logger.warning(
            "No valid manifests found in the paths. Nyl does not recursively enumerate directory contents, make sure "
            "you are specifying at least one path with valid YAML manifests to render.",
            paths,
        )

    result = []
    for file in files:
        manifests = Manifests(list(map(Manifest, filter(None, yaml.loads_all(file.read_text())))))
        result.append(ManifestsWithSource(manifests, file))

    return result

    #     # Check if the resource has any references and try to resolve them. If a reference cannot be resolved, the
    #     # manifest must be skipped. We emit a warning and continue with the next manifest.
    #     refs = list(Reference.collect(manifest))
    #     if refs:
    #         skip_resource = False
    #         resolves = {}
    #         for ref in refs:
    #             # TODO: Determine the namespace to fall back to.
    #             try:
    #                 result = k8s.get(
    #                     resource=k8s.resources.get(api_version="v1", kind=ref.kind, group=""),
    #                     name=ref.name,
    #                     namespace=ref.namespace,  # TODO: Determine the namespace to backfill to.
    #                 )

    #                 value = result["data"][ref.key]
    #                 if value is None:
    #                     raise KeyError
    #                 assert isinstance(value, str)
    #                 resolves[str(ref)] = base64.b64decode(value.encode("ascii")).decode("utf-8")
    #             except NotFoundError:
    #                 logger.warning(
    #                     "Skipping resource {}/{} because its reference to {} could not be resolved.",
    #                     manifest["apiVersion"],
    #                     manifest["kind"],
    #                     ref,
    #                 )
    #                 skip_resource = True
    #                 break
    #             except KeyError:
    #                 logger.warning(
    #                     "Skipping resource {}/{} because its reference to {} could not be resolved (does not contain key {}).",
    #                     manifest["apiVersion"],
    #                     manifest["kind"],
    #                     ref,
    #                     ref.key,
    #                 )
    #                 skip_resource = True
    #                 break
    #         if skip_resource:
    #             continue
    #         manifest = Reference.sub(manifest, lambda ref: resolves[str(ref)])


def is_namespace_resource(manifest: Manifest) -> bool:
    """
    Check if a manifest is a namespace resource.
    """

    return manifest.get("apiVersion") == "v1" and manifest.get("kind") == "Namespace"


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

    namespace_resources = [x for x in source.manifests if is_namespace_resource(x)]

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
        logger.debug("Manifest '{}' defines exactly one Namespace resource. Using '{}' as the default namespace.")
        return namespace_resources[0]["metadata"]["name"]  # type: ignore[no-any-return]

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
        return use_namespace

    if len(default_namespaces) > 1:
        logger.error(
            "Manifest '{}' defines {} namespaces, but more than one of them have the `{}` label. "
            "The following namespaces have the `{}` label: {}",
            source.file,
            len(namespace_resources),
            DEFAULT_NAMESPACE_ANNOTATION,
            ", ".join(default_namespaces),
        )
        exit(1)

    return default_namespaces.pop()  # type: ignore[no-any-return]
