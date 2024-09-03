"""
This package contains everything related to the generation of Kubernetes manifests via Nyl.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, Generic, TypeVar

from nyl.resources import API_VERSION_INLINE
from nyl.tools.types import Manifest, Manifests

T = TypeVar("T")


class Generator(ABC, Generic[T]):
    """
    Base class for generating Kubernetes manifests from Nyl resources.
    """

    resource_type: ClassVar[type[Any]]

    def __init_subclass__(cls, resource_type: type[T], **kwargs: Any) -> None:
        cls.resource_type = resource_type
        super().__init_subclass__(**kwargs)

    @abstractmethod
    def generate(self, /, resource: T) -> Manifests:
        """
        Evaluate a Nyl resource and return a list of the generated Kubernetes manifests.
        """

        raise NotImplementedError


def reconcile_generator(
    generator: Generator[Manifest],
    manifests: Manifests,
    on_generated: Callable[[Manifest], Manifest],
) -> Manifests:
    """
    Recursively reconcile all Nyl resources in the manifests using the given generator.

    Args:
        generator: The generator to use for generating manifests from Nyl resources.
        manifests: The list of manifests to reconcile.
        on_generated: A callback to call on each generated manifest, giving the opportunity to modify it.
                      This is used to pass the manifest through the `structured-templates` engine.
    """

    queue = Manifests(manifests)
    result = Manifests([])
    loops = 0

    while queue:
        if loops > 1000:
            raise RuntimeError("Reconciliation loop limit exceeded (1000).")

        resource = queue.pop(0)
        if resource.get("apiVersion") == API_VERSION_INLINE:
            for manifest in generator.generate(resource):
                queue.append(on_generated(manifest))
        else:
            result.append(resource)
        loops += 1

    return result
