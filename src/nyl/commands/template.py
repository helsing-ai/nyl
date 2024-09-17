import atexit
from dataclasses import dataclass
import os
from pathlib import Path
from textwrap import indent
from typing import Optional
from loguru import logger
from typer import Argument, Option
import yaml
from nyl.generator import reconcile_generator
from nyl.generator.dispatch import DispatchingGenerator
from nyl.profiles import ProfileManager
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config
from kubernetes.client.api_client import ApiClient
from nyl.project.config import ProjectConfig
from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.resources.applyset import APPLYSET_LABEL_PART_OF, ApplySet
from nyl.secrets.config import SecretsConfig
from nyl.templating import NylTemplateEngine
from nyl.tools.kubectl import Kubectl
from nyl.tools.logging import lazy_str
from nyl.tools.types import Manifest, Manifests

from . import app

DEFAULT_PROFILE = "default"


@dataclass
class ManifestsWithSource:
    """
    Represents a list of manifests loaded from a particular source file.
    """

    manifests: Manifests
    file: Path


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
    state_dir: Optional[Path] = Option(
        None, help="The directory to store state in (such as kubeconfig files).", envvar="NYL_STATE_DIR"
    ),
    cache_dir: Optional[Path] = Option(
        None,
        help="The directory to store cache data in. If not set, a directory in the --state-dir is used.",
        envvar="NYL_CACHE_DIR",
    ),
) -> None:
    """
    Render a package template into full Kubernetes resources.
    """

    if paths == [Path(".")] and (env_paths := os.getenv("ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT")) is not None:
        paths = [Path(p) for p in env_paths.split(",")]
        if not paths:
            logger.error("<cyan>ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT</> is set, but empty.")
            exit(1)
        logger.opt(ansi=True).info(
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
    if in_cluster:
        logger.info("Using in-cluster configuration.")
        load_incluster_config()
    else:
        with ProfileManager.load(required=False) as profiles:
            # If no profile to activate is specified, and there are no profiles defined, we're not activating a
            # a profile. It should be valid to use Nyl without a `nyl-profiles.yaml` file.
            if profile is not None or profiles.config.profiles:
                profile = profile or DEFAULT_PROFILE
                active = profiles.activate_profile(profile)
                load_kube_config(str(active.kubeconfig))
            else:
                logger.opt(ansi=True).info(
                    "No <yellow>nyl-profiles.yaml</> file found, using default kubeconfig and context."
                )
                load_kube_config()

    project = ProjectConfig.load()
    if generate_applysets is not None:
        project.config.settings.generate_applysets = generate_applysets

    if state_dir is None:
        state_dir = project.file.parent / ".nyl" if project.file else Path(".nyl")

    if cache_dir is None:
        cache_dir = state_dir / "cache"

    secrets = SecretsConfig.load()
    client = ApiClient()

    template_engine = NylTemplateEngine(
        secrets.providers[secrets_provider], client, create_placeholders=project.config.settings.generate_placeholders
    )

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
        logger.opt(ansi=True).info("Rendering manifests from <blue>{}</>.", source.file)

        source.manifests = template_engine.evaluate(source.manifests)
        if inline:
            source.manifests = reconcile_generator(
                generator,
                source.manifests,
                on_generated=lambda m: template_engine.evaluate(Manifests([m])),
            )

        # Find the namespaces that are defined in the file. If we find any manifests without a namespace, we will
        # inject that namespace name into them. Also find the applyset defined in the file.
        namespaces: set[str] = set()
        applyset: ApplySet | None = None

        for manifest in list(source.manifests):
            if is_namespace_resource(manifest):
                namespaces.add(manifest["metadata"]["name"])
            elif ApplySet.matches(manifest):
                if applyset is not None:
                    logger.opt(ansi=True).error(
                        "Multiple ApplySet resources defined in <yellow>{}</>, there can only be one per source.",
                        source.file,
                    )
                    exit(1)
                applyset = ApplySet.load(manifest)
                source.manifests.remove(manifest)

        # Determine what namespace to fill in if we encounter resources without it.
        current_default_namespace = default_namespace
        if current_default_namespace is None:
            if len(namespaces) == 1:
                current_default_namespace = next(iter(namespaces))
            elif len(namespaces) == 0:
                current_default_namespace = source.file.stem
        elif len(namespaces) > 2 and current_default_namespace not in namespaces:
            logger.error(
                "The specified --default-namespace='{}' is not defined in manifest source file '{}', despite it "
                "defining {} namespaces. If your manifest source file defines multiple namespaces, the specified "
                "--default-namespace must be one of the namespaces defined in it (the file current defines "
                "the following namespaces: {})",
                default_namespace,
                source.file,
                len(namespaces),
                ", ".join(namespaces),
            )
            exit(1)

        if not applyset and project.config.settings.generate_applysets:
            if not current_default_namespace:
                logger.opt(ansi=True).error(
                    "No default namespace defined for <yellow>{}</>, but it is required for the automatically "
                    "generated nyl.io/v1/ApplySet resource (the ApplySet is named after the default namespace).",
                    source.file,
                )
                exit(1)

            applyset_name = current_default_namespace
            applyset = ApplySet.new(applyset_name)
            logger.opt(ansi=True).info(
                "Automatically creating ApplySet for <blue>{}</> (name: <magenta>{}</>).", source.file, applyset_name
            )

        if applyset is not None:
            applyset.set_group_kinds(source.manifests)
            # HACK: Kubectl 1.30 can't create the custom resource, so we need to create it. But it will also reject
            #       using the custom resource unless it has the tooling label set appropriately. For more details, see
            #       https://github.com/NiklasRosenstein/nyl/issues/5.
            applyset.tooling = f"kubectl/v{generator.kube_version}"
            applyset.validate()

            if apply:
                # We need to ensure that ApplySet parent object exists before invoking `kubectl apply --applyset=...`.
                logger.opt(ansi=True).info(
                    "Kubectl-apply ApplySet resource <yellow>{}</> from <cyan>{}</>.",
                    applyset.reference,
                    source.file,
                )
                kubectl.apply(Manifests([applyset.dump()]), force_conflicts=True)
            elif diff:
                kubectl.diff(Manifests([applyset.dump()]))
            else:
                print("---")
                print(yaml.safe_dump(applyset.dump()))

        # Find all manifests without a namespace and inject the namespace name into them.
        # If there is an applyset, ensure they are marked as part of the applyset.
        for manifest in source.manifests:
            # Inline resources often don't have metadata and they are not persisted to the cluster, hence
            # we don't need to process them here.
            if NylResource.matches(manifest, API_VERSION_INLINE):
                assert not inline, "Inline resources should have been processed by this timepdm lint."
                continue

            if "metadata" not in manifest:
                logger.opt(ansi=True).error(
                    "A manifest in <yellow>'{}'</> has no <cyan>metadata</> key:\n\n{}",
                    source.file,
                    indent(yaml.safe_dump(manifest), "  "),
                )
                exit(1)

            if applyset is not None and applyset_part_of:
                if APPLYSET_LABEL_PART_OF not in (labels := manifest["metadata"].setdefault("labels", {})):
                    labels[APPLYSET_LABEL_PART_OF] = applyset.id

            if not is_cluster_scoped_resource(manifest) and "namespace" not in manifest["metadata"]:
                if not current_default_namespace:
                    logger.error(
                        "A namespace-scoped manifest in '{}' has no namespace, and no default namespace is defined. "
                        "Try defining a single namespace in the manifest source file, naming the manifest source file "
                        "the same as that default namespace or passing the --default-namespace option.",
                        source.file,
                    )
                    exit(1)

                logger.trace(
                    "Injecting namespace '{}' into manifest {}/{}.",
                    current_default_namespace,
                    manifest["kind"],
                    manifest["metadata"]["name"],
                )
                manifest["metadata"]["namespace"] = current_default_namespace

            elif not is_cluster_scoped_resource(manifest) and manifest["metadata"]["namespace"] not in namespaces:
                logger.warning(
                    "Resource '{}/{}' in '{}' references namespace '{}', which is not defined in the file.",
                    manifest["kind"],
                    manifest["metadata"]["name"],
                    source.file,
                    manifest["metadata"]["namespace"],
                )

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
                print(yaml.safe_dump(manifest))


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

    result = []
    for file in files:
        manifests = Manifests(list(map(Manifest, filter(None, yaml.safe_load_all(file.read_text())))))
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


def is_cluster_scoped_resource(manifest: Manifest) -> bool:
    """
    Check if a manifest is a cluster scoped resource.
    """

    # HACK: We should probably just list the resources via the Kubectl API?
    fqn = manifest.get("kind", "") + "." + manifest.get("apiVersion", "").split("/")[0]
    return fqn in {
        "ClusterRole.rbac.authorization.k8s.io",
        "ClusterRoleBinding.rbac.authorization.k8s.io",
        "CustomResourceDefinition.apiextensions.k8s.io",
        "IngressClass.networking.k8s.io",
        "Namespace.v1",
        "StorageClass.storage.k8s.io",
        "ValidatingWebhookConfiguration.admissionregistration.k8s.io",
    }
