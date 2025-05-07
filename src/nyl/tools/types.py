from typing import Any, Callable, NewType, TypeVar

T = TypeVar("T")

Provider = Callable[[], T]
""" Represents a provider function that returns an instance of a type. """

Resource = NewType("Resource", dict[str, Any])
""" Represents a Kubernetes resource. """

ResourceList = NewType("ResourceList", list[Resource])
""" Represents a list of Kubernetes resources. """
