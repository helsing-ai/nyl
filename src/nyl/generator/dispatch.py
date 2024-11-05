from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from kubernetes.client import VersionApi
from kubernetes.client.api_client import ApiClient
from nyl.generator import Generator
from nyl.generator.components import ComponentsGenerator
from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.tools.kubernetes import discover_kubernetes_api_versions
from nyl.tools.types import Manifest, Manifests


@dataclass
class DispatchingGenerator(Generator[Manifest], resource_type=Manifest):
    """
    Dispatches to the appropriate generator based on the resource type.

    Any resources can be passed to this generator, but only resources that have a corresponding generator will be
    processed. Any other resources will be returned as-is.
    """

    kube_version: str
    """ The Kubernetes API version. """

    generators: dict[str, Generator[Any]] = field(default_factory=dict)
    """ Collection of generators to dispatch to based on the resource kind. """

    fallback: Generator[Any] | None = None
    """ Generator to use for any apiVersions that don't match `NylResource` (e.g. for 'Nyl components'). """

    @staticmethod
    def default(
        *,
        cache_dir: Path,
        search_path: list[Path],
        components_path: Path,
        working_dir: Path,
        client: ApiClient,
        kube_version: str | None = None,
        kube_api_versions: set[str] | str | None = None,
    ) -> "DispatchingGenerator":
        """
        Create a new DispatchingGenerator with the default set of generators.

        Args:
            cache_dir: A directory where caches can be stored.
            search_path: A list of directories to search for Helm charts in if the chart path is not explicitly
                         absolute or relative.
            components_path: Path to search for Nyl components.
            working_dir: The working directory to consider relative paths relative to.
            client: The Kubernetes API client to use for interacting with the Kubernetes API.
            kube_version: The Kubernetes API version to generate manifests for. If not specified, the version will be
                          determined from the Kubernetes API server.
            kube_api_versions: The Kubernetes API versions supported by the cluster. If not specified, the versions
                               will be determined from the Kubernetes API server.
        """

        from nyl.generator.helmchart import HelmChartGenerator
        from nyl.generator.statefulsecret import StatefulSecretGenerator

        if kube_version is None:
            version_info = VersionApi(client).get_code()
            kube_version = f"{version_info.major}.{version_info.minor.rstrip('+')}"
            logger.debug("Determined Kubernetes version: {}", kube_version)

        if kube_api_versions is None:
            kube_api_versions = discover_kubernetes_api_versions(client)
        else:
            if isinstance(kube_api_versions, str):
                kube_api_versions = set(kube_api_versions.split(","))

        helm_generator = HelmChartGenerator(
            git_repo_cache_dir=cache_dir / "git-repos",
            chart_cache_dir=cache_dir / "helm-charts",
            search_path=search_path,
            working_dir=working_dir,
            kube_version=kube_version,
            api_versions=kube_api_versions,
        )

        return DispatchingGenerator(
            kube_version=kube_version,
            generators={
                "HelmChart": helm_generator,
                "StatefulSecret": StatefulSecretGenerator(client),
            },
            fallback=ComponentsGenerator(
                search_path=[components_path],
                helm_generator=helm_generator,
            ),
        )

    # Generator implementation

    def generate(self, /, res: Manifest) -> Manifests:
        if res["apiVersion"] != API_VERSION_INLINE:
            if self.fallback:
                return self.fallback.generate(res)
            return Manifests([res])

        nyl_resource = NylResource.load(res)
        if nyl_resource.KIND not in self.generators:
            raise ValueError(f"No generator found for resource kind: {nyl_resource.KIND}")

        generator = self.generators[nyl_resource.KIND]
        return generator.generate(nyl_resource)
