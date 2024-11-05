"""
Tools for dependency injection.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


class DependenciesProvider(ABC):
    """
    A simple interface for looking up an object by its type.
    """

    @abstractmethod
    def get(self, object_type: type[T]) -> T:
        """
        Args:
            object_type: The Python type of the object to get.
        Returns:
            An object matching the type, may be a subtype.
        Raises:
            DependencyNotSatisfiedError: If no object for the given type can be provided.
        """

        raise RuntimeError(f"{type(self).__name__}.get() not implemented")

    @staticmethod
    def default() -> "DefaultDependenciesProvider":
        """
        Simple factory function to avoid importing more names.
        """

        return DefaultDependenciesProvider()


class DefaultDependenciesProvider(DependenciesProvider):
    def __init__(self) -> None:
        self._eager_registry: dict[type[Any], Any] = {}
        self._lazy_registry: dict[type[Any], Callable[[], Any]] = {}

    def __repr__(self) -> str:
        if not self._eager_registry and not self._lazy_registry:
            return f"<{type(self).__name__} empty>"
        else:
            return (
                f"<{type(self).__name__} len(eager)={len(self._eager_registry)} len(lazy)={len(self._lazy_registry)}>"
            )

    def set(self, object_type: type[T], obj: T) -> None:
        """
        Set an object to be returned when the given object type is requested.
        """

        self._eager_registry[object_type] = obj

    def set_lazy(self, object_type: type[T], func: Callable[[], T]) -> None:
        """
        Set a function to be called at most once when the given object type is requested.
        """

        self._lazy_registry[object_type] = func

    # DependenciesProvider

    def get(self, object_type: type[T]) -> T:
        if object_type in self._eager_registry:
            return cast(T, self._eager_registry[object_type])
        elif object_type in self._lazy_registry:
            result = self._lazy_registry[object_type]()
            self._eager_registry[object_type] = result
            return cast(T, result)
        else:
            raise DependencyNotSatisfiedError(object_type)


class DependencyNotSatisfiedError(RuntimeError):
    def __init__(self, object_type: type[T]) -> None:
        self.object_type = object_type

    def __str__(self) -> str:
        typename = self.object_type.__module__ + "." + self.object_type.__qualname__
        return f"No object is available for the requested type '{typename}'"
