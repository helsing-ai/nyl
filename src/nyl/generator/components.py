"""
Implements Nyl components generation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Sequence

from databind.core import Remainder
from databind.json import load as deser
from loguru import logger

from nyl.generator import Generator
from nyl.generator.helmchart import HelmChartGenerator
from nyl.resources import ObjectMetadata
from nyl.resources.helmchart import ChartRef, HelmChart, HelmChartSpec
from nyl.tools.types import Manifest, Manifests


class Component:
    pass


@dataclass
class HelmComponent(Component):
    path: Path


@dataclass
class GenericComponent(Component):
    apiVersion: str
    kind: str
    metadata: ObjectMetadata
    spec: dict[str, Any] = field(default_factory=dict)

    # Additional fields, which are not allowed in the schema, but are stored and later checked if set.
    # Having additional fields on a resource for which we find a component is an error.
    remainder: Annotated[dict[str, Any], Remainder()] = field(default_factory=dict)


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
        instance = deser(resource, GenericComponent)
        component = self.find_component(instance.apiVersion, instance.kind)
        if component is None:
            return Manifests([resource])

        if instance.remainder:
            raise RuntimeError(f"unexpected fields in component {instance.metadata}: {instance.remainder.keys()}")

        match component:
            case HelmComponent(path):
                chart = HelmChart(
                    metadata=instance.metadata,
                    spec=HelmChartSpec(
                        chart=ChartRef(path=str(path.resolve())),
                        values={"metadata": resource["metadata"], **instance.spec},
                    ),
                )
                return self.helm_generator.generate(chart)
            case _:
                raise RuntimeError(f"unexpected component type: {component}")
