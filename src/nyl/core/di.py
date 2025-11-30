"""Dependency injection container for Nyl.

This module provides a request-scoped dependency injection container that
replaces the global singleton pattern. Each CLI invocation creates its own
container, making the system more testable and maintainable.
"""

from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")


class DIContainer:
    """Request-scoped dependency injection container.

    Features:
    - Factory registration for lazy initialization
    - Singleton registration for pre-configured instances
    - Hierarchical scopes with parent containers
    - Type-safe resolution

    Example:
        >>> class Database:
        ...     def __init__(self, url: str):
        ...         self.url = url
        ...
        >>> container = DIContainer()
        >>> container.register_factory(Database, lambda: Database(url="..."))
        >>> db = container.resolve(Database)
        >>> assert db.url == "..."
    """

    def __init__(self, parent: "DIContainer | None" = None):
        """Create a new DI container.

        Args:
            parent: Optional parent container for hierarchical scopes
        """
        self._instances: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._parent = parent

    def register_factory(self, type_: type[T], factory: Callable[[], T]) -> None:
        """Register a factory function for a type.

        The factory will be called once when the type is first resolved,
        and the result will be cached for subsequent resolutions.

        Args:
            type_: The type to register
            factory: A callable that creates an instance of the type
        """
        self._factories[type_] = factory

    def register_singleton(self, type_: type[T], instance: T) -> None:
        """Register a pre-configured singleton instance.

        Args:
            type_: The type to register
            instance: The singleton instance
        """
        self._instances[type_] = instance

    def resolve(self, type_: type[T]) -> T:
        """Resolve an instance of the specified type.

        Resolution order:
        1. Check if instance already exists in cache
        2. Check if factory exists and create instance
        3. Check parent container (if exists)
        4. Raise KeyError if not found

        Args:
            type_: The type to resolve

        Returns:
            An instance of the requested type

        Raises:
            KeyError: If the type is not registered
        """
        # Check cache first
        if type_ in self._instances:
            return cast(T, self._instances[type_])

        # Try to create from factory
        if type_ in self._factories:
            instance = self._factories[type_]()
            self._instances[type_] = instance
            return cast(T, instance)

        # Try parent container
        if self._parent:
            return self._parent.resolve(type_)

        # Not found
        raise KeyError(f"No registration found for type {type_.__name__}")

    def has(self, type_: type) -> bool:
        """Check if a type is registered in this container or its parents.

        Args:
            type_: The type to check

        Returns:
            True if the type is registered, False otherwise
        """
        if type_ in self._instances or type_ in self._factories:
            return True
        if self._parent:
            return self._parent.has(type_)
        return False

    def create_scope(self) -> "DIContainer":
        """Create a child container that inherits from this container.

        The child container can resolve types from this parent but has
        its own instance cache. This is useful for creating request-scoped
        or operation-scoped containers.

        Returns:
            A new DIContainer with this container as parent
        """
        return DIContainer(parent=self)

    def clear(self) -> None:
        """Clear all instances and factories.

        This is primarily useful for testing.
        """
        self._instances.clear()
        self._factories.clear()
