import atexit
from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from typing import Optional, cast
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
    in_cluster: bool = Option(
        False, help="Use the in-cluster Kubernetes configuration. The --profile option is ignored."
    ),
    apply: bool = Option(
        False,
        help="Run `kubectl apply` on the rendered manifests, once for each source file. "
        "Implies `--no-applyset-part-of`. When an ApplySet is defined in the source file, it will be applied "
        "separately. Note that this option implies `kubectl --prune`.",
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

    if apply:
        # When running with --apply, we must ensure that the --applyset-part-of option is disabled, as it would cause
        # an error when passing the generated manifests to `kubectl apply --applyset=...`.
        applyset_part_of = False

    kubectl = Kubectl()
    kubectl.env["KUBECTL_APPLYSET"] = "true"
    atexit.register(kubectl.cleanup)

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
        project.config.generate_applysets = generate_applysets

    if state_dir is None:
        state_dir = project.file.parent / ".nyl" if project.file else Path(".nyl")

    if cache_dir is None:
        cache_dir = state_dir / "cache"

    secrets = SecretsConfig.load()
    client = ApiClient()

    template_engine = NylTemplateEngine(secrets.provider, client)

    generator = DispatchingGenerator.default(
        cache_dir=cache_dir,
        search_path=project.config.search_path,
        working_dir=Path.cwd(),
        client=client,
    )

    for source in load_manifests(paths):
        logger.opt(ansi=True).info("Rendering manifests from <blue>{}</>.", source.file)

        source.manifests = cast(Manifests, template_engine.evaluate(source.manifests))
        if inline:
            source.manifests = reconcile_generator(
                generator,
                source.manifests,
                on_generated=lambda m: cast(Manifest, template_engine.evaluate(m)),
            )

        # Find the namespaces that are defined in the file. If we find any manifests without a namespace, we will
        # inject that namespace name into them.
        # Also find the applyset defined in the file.
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

        if not applyset and project.config.generate_applysets:
            if len(namespaces) > 1:
                logger.opt(ansi=True).error(
                    "Multiple namespaces defined in <yellow>{}</>, but automatic ApplySet generation is enabled. "
                    "There can only be one namespace per source in this case.",
                    source.file,
                )
                exit(1)
            elif len(namespaces) == 1:
                applyset_name = next(iter(namespaces))
            else:
                applyset_name = source.file.stem

            logger.opt(ansi=True).info(
                "Automatically creating ApplySet for <blue>{}</> (name: <magenta>{}</>).", source.file, applyset_name
            )
            applyset = ApplySet.new(applyset_name)

        if applyset is not None:
            applyset.set_group_kinds(source.manifests)
            # HACK: Kubectl 1.30 can't create the custom resource, so we need to create it. But it will also reject
            #       using the custom resource unless it has the tooling label set appropriately. For more details, see
            #       https://github.com/NiklasRosenstein/nyl/issues/5.
            applyset.tooling = "kubectl/v1.30.0"
            applyset.validate()

            if apply:
                # We need to ensure that ApplySet parent object exists before invoking `kubectl apply --applyset=...`.
                logger.opt(ansi=True).info(
                    "Kubectl-apply ApplySet resource <yellow>{}</> from <cyan>{}</>.",
                    applyset.reference,
                    source.file,
                )
                kubectl.apply(Manifests([applyset.dump()]), force_conflicts=True)
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
                    "Manifest in <yellow>'{}'</> has no <cyan>metadata</> key:\n\n{}",
                    source.file,
                    indent(yaml.safe_dump(manifest), "  "),
                )
                exit(1)

            if applyset is not None and applyset_part_of:
                if APPLYSET_LABEL_PART_OF not in (labels := manifest["metadata"].setdefault("labels", {})):
                    labels[APPLYSET_LABEL_PART_OF] = applyset.id

            if not is_cluster_scoped_resource(manifest) and "namespace" not in manifest["metadata"]:
                if len(namespaces) > 1:
                    logger.error(
                        "Multiple namespaces defined in '{}', but manifest {}/{} does not have a namespace.",
                        source.file,
                        manifest["kind"],
                        manifest["metadata"]["name"],
                    )
                    exit(1)
                elif len(namespaces) == 0:
                    logger.warning(
                        "No namespaces defined in '{}', injecting 'default' into manifest {}/{}.",
                        source.file,
                        manifest["kind"],
                        manifest["metadata"]["name"],
                    )
                    manifest["metadata"]["namespace"] = "default"
                else:
                    logger.trace(
                        "Injecting namespace '{}' into manifest {}/{}.",
                        next(iter(namespaces)),
                        manifest["kind"],
                        manifest["metadata"]["name"],
                    )
                    manifest["metadata"]["namespace"] = next(iter(namespaces))
            elif not is_cluster_scoped_resource(manifest) and manifest["metadata"]["namespace"] not in namespaces:
                logger.warning(
                    "Resource '{}/{}' in '{}' references namespace '{}', which is not defined in the file.",
                    manifest["kind"],
                    manifest["metadata"]["name"],
                    source.file,
                    manifest["metadata"]["namespace"],
                )

        if not apply:
            # If we're not going to be applying the manifests immediately via `kubectl`, we print them to stdout.
            for manifest in source.manifests:
                print("---")
                print(yaml.safe_dump(manifest))

        if apply:
            logger.info("Kubectl-apply {} manifest(s) from '{}'", len(source.manifests), source.file)
            kubectl.apply(
                manifests=source.manifests,
                applyset=applyset.reference if applyset else None,
                prune=True if applyset else False,
                force_conflicts=True,
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
