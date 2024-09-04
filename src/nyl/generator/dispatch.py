from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from nyl.generator import Generator
from nyl.resources import NylResource
from nyl.tools.kubernetes import discover_kubernetes_api_versions
from nyl.tools.types import Manifest, Manifests
from kubernetes.client import VersionApi
from kubernetes.client.api_client import ApiClient


@dataclass
class DispatchingGenerator(Generator[Manifest], resource_type=Manifest):
    """
    Dispatches to the appropriate generator based on the resource type.

    Any resources can be passed to this generator, but only resources that have a corresponding generator will be
    processed. Any other resources will be returned as-is.
    """

    generators: dict[str, Generator[Any]] = field(default_factory=dict)
    """ Collection of generators to dispatch to based on the resource kind. """

    @staticmethod
    def default(
        *,
        cache_dir: Path,
        search_path: list[Path],
        working_dir: Path,
        client: ApiClient,
        kube_version: str | None = None,
    ) -> "DispatchingGenerator":
        """
        Create a new DispatchingGenerator with the default set of generators.

        Args:
            cache_dir: A directory where caches can be stored.
            search_path: A list of directories to search for Helm charts in if the chart path is not explicitly
                         absolute or relative.
            working_dir: The working directory to consider relative paths relative to.
            client: The Kubernetes API client to use for interacting with the Kubernetes API.
            kube_version: The Kubernetes API version to generate manifests for. If not specified, the version will be
                          determined from the Kubernetes API server.
        """

        from nyl.generator.helmchart import HelmChartGenerator
        from nyl.generator.statefulsecret import StatefulSecretGenerator

        if kube_version is None:
            version_info = VersionApi(client).get_code()
            kube_version = f"{version_info.major}.{version_info.minor.rstrip('+')}"
            logger.debug("Determined Kubernetes version: {}", kube_version)

        return DispatchingGenerator(
            generators={
                "HelmChart": HelmChartGenerator(
                    git_repo_cache_dir=cache_dir / "git-repos",
                    chart_cache_dir=cache_dir / "helm-charts",
                    search_path=search_path,
                    working_dir=working_dir,
                    kube_version=kube_version,
                    api_versions=discover_kubernetes_api_versions(client),
                ),
                "StatefulSecret": StatefulSecretGenerator(client),
            }
        )

    # Generator implementation

    def generate(self, /, res: Manifest) -> Manifests:
        if (nyl_resource := NylResource.maybe_load(res)) is None:
            return Manifests([res])

        if nyl_resource.KIND not in self.generators:
            raise ValueError(f"No generator found for resource kind: {nyl_resource.KIND}")

        generator = self.generators[nyl_resource.KIND]
        return generator.generate(nyl_resource)
