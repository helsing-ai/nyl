"""
Implements Nyl components generation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from loguru import logger
from nyl.generator import Generator
from nyl.generator.helmchart import HelmChartGenerator
from nyl.resources.helmchart import ChartRef, HelmChart, ReleaseMetadata
from nyl.tools.types import Manifest, Manifests


class Component:
    pass


@dataclass
class HelmComponent(Component):
    path: Path


@dataclass
class ComponentsGenerator(Generator[Manifest], resource_type=Manifest):
    search_path: Sequence[Path]
    """ A list of directories to search for a matching Nyl component. """

    helm_generator: HelmChartGenerator
    """ The generator to use when encountering a Helm Nyl component. """

    def __post_init__(self) -> None:
        self._component_cache: dict[tuple[str, str], Component | None] = {}

    def find_component(self, api_version: str, kind: str) -> Component | None:
        key = (api_version, kind)
        if key in self._component_cache:
            return self._component_cache[key]

        component: Component | None = None
        for path in self.search_path:
            path = path / api_version / kind
            chart_yaml = path / "Chart.yaml"
            if chart_yaml.is_file():
                component = HelmComponent(path)
                break

        if component:
            logger.debug("Found Nyl component for '{}/{}': {}", api_version, kind, component)
        self._component_cache[key] = component
        return component

    # Generator

    def generate(self, /, resource: Manifest) -> Manifests:
        api_version = resource["apiVersion"]
        kind = resource["kind"]

        component = self.find_component(api_version, kind)
        match component:
            case None:
                return Manifests([resource])
            case HelmComponent(path):
                chart = HelmChart(
                    chart=ChartRef(path=str(path.resolve())),
                    release=ReleaseMetadata(
                        name=resource["metadata"]["name"],
                        namespace=resource["metadata"].get("namespace", None),
                    ),
                    values=resource.get("spec", {}),
                )
                return self.helm_generator.generate(chart)
            case _:
                raise RuntimeError(f"unexpected component type: {component}")
