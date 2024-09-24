from collections.abc import Sequence
from typing import Any, Iterator

from kubernetes.dynamic.client import DynamicClient

class Resource:
    prefix: str
    group: str
    api_version: str
    kind: str
    namespaced: bool
    verbs: Sequence[str]
    name: str
    preferred: bool
    client: DynamicClient
    singular_name: str
    short_names: Sequence[str]
    categories: Sequence[str]
    subresources: dict[str, "Subresource"]
    extra_args: dict[str, Any]

    def to_dict(self) -> dict[str, Any]: ...
    @property
    def group_version(self) -> str: ...
    def path(self, name: str | None = None, namespace: str | None = None) -> str: ...
    def get(self, name: str, namespace: str | None = None) -> "ResourceInstance": ...

class Subresource(Resource):
    parent: Resource
    subresource: str

class ResourceField:
    def __getitem__(self, key: str) -> ResourceField | Any: ...
    def __iter__(self) -> Iterator[tuple[str, Any]]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def to_str(self) -> str: ...

class ResourceInstance:
    client: DynamicClient
    attributes: ResourceField

    def __getitem__(self, key: str) -> ResourceField | Any: ...
    def to_dict(self) -> dict[str, Any]: ...
