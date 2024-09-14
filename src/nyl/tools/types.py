from typing import Any, Callable, NewType, TypeVar

T = TypeVar("T")

Provider = Callable[[], T]
""" Represents a provider function that returns an instance of a type. """

Manifest = NewType("Manifest", dict[str, Any])
""" Represents a Kubernetes manifest. """

Manifests = NewType("Manifests", list[Manifest])
""" Represents a list of Kubernetes manifests. """
