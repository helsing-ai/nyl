from typing import Any, Iterable, Protocol

from kubernetes.client.api_client import ApiClient
from kubernetes.dynamic.discovery import Discoverer
from kubernetes.dynamic.resource import Resource, ResourceInstance
from kubernetes.watch import Watch

class _ToDict(Protocol):
    def to_dict(self) -> dict[str, Any]: ...

class DynamicClient:
    def __init__(self, client: ApiClient) -> None: ...
    @property
    def resources(self) -> Discoverer: ...
    def get(
        self, resource: Resource, name: str | None = None, namespace: str | None = None, **kwargs: dict[str, Any]
    ) -> ResourceInstance: ...
    def create(
        self,
        resource: Resource,
        body: _ToDict | dict[str, Any] | None = None,
        namespace: str | None = None,
        **kwargs: dict[str, Any],
    ) -> ResourceInstance: ...
    def delete(
        self,
        resource: Resource,
        name: str | None = None,
        namespace: str | None = None,
        body: _ToDict | dict[str, Any] | None = None,
        label_selector: str | None = None,
        field_selector: str | None = None,
        **kwargs: dict[str, Any],
    ) -> None: ...  # TODO: What does this return?
    def replace(
        self,
        resource: Resource,
        body: _ToDict | dict[str, Any],
        name: str | None = None,
        namespace: str | None = None,
        **kwargs: dict[str, Any],
    ) -> ResourceInstance: ...
    def patch(
        self,
        resource: Resource,
        body: _ToDict | dict[str, Any],
        name: str | None = None,
        namespace: str | None = None,
        **kwargs: dict[str, Any],
    ) -> ResourceInstance: ...
    def server_side_apply(
        self,
        resource: Resource,
        body: _ToDict | dict[str, Any],
        name: str | None = None,
        namespace: str | None = None,
        force_conflicts: bool | None = None,
        **kwargs: dict[str, Any],
    ) -> ResourceInstance: ...
    def watch(
        self,
        resource: Resource,
        namespace: str | None = None,
        name: str | None = None,
        label_selector: str | None = None,
        field_selector: str | None = None,
        resource_version: str | None = None,
        timeout: float | None = None,
        watcher: Watch | None = None,
        **kwargs: dict[str, Any],
    ) -> Iterable[dict[str, Any]]: ...
