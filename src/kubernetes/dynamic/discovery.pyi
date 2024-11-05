from collections.abc import Sequence
from typing import Any

from kubernetes.dynamic.resource import Resource

class Discoverer:
    def invalidate_cache(self) -> None: ...

    # @property
    # def api_groups(self) -> ...: ...

    def search(
        self,
        prefix: str | None = None,
        group: str | None = None,
        api_version: str | None = None,
        kind: str | None = None,
        **kwargs: Any,
    ) -> Sequence[Resource]: ...
    def discover(self) -> None: ...
    @property
    def version(self) -> str: ...
    def get(
        self,
        prefix: str | None = None,
        group: str | None = None,
        api_version: str | None = None,
        kind: str | None = None,
        **kwargs: Any,
    ) -> Resource: ...
