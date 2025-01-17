"""
This package contains Nyl's own Kubernetes-esque resources.
"""

from abc import ABC
from dataclasses import dataclass
from typing import ClassVar, Collection, cast

from databind.core import SerializeDefaults
from databind.json import dump as ser
from databind.json import load as deser
from typing_extensions import Self

from nyl.tools.types import Manifest

API_VERSION_K8S = "nyl.io/v1"
API_VERSION_INLINE = "inline.nyl.io/v1"


class NylResource(ABC):
    """
    Base class for Nyl custom resources.
    """

    API_VERSION: ClassVar[str]
    """
    The API version of the resource. This is usually `inline.nyl.io/v1` for resources that are inlined by Nyl at
    templating time and are not present in the final manifest, or `nyl.io/v1` for resources that are actual Kubernetes
    resources.
    """

    KIND: ClassVar[str]
    """
    The kind identifier of the resource. If not set, this will default to the class name.
    """

    def __init_subclass__(cls, api_version: str, kind: str | None = None) -> None:
        cls.API_VERSION = api_version
        if kind is not None or "KIND" not in vars(cls):
            cls.KIND = kind or cls.__name__

    @classmethod
    def load(cls, manifest: Manifest) -> "Self":
        """
        Load a Nyl resource from a manifest. If called directly on `NylResource`, this will deserialize into the
        appropriate subclass based on the `kind` field in the manifest. If the method is instead called on a subclass
        directly, the subclass will be used to deserialize the manifest.
        """

        if manifest.get("apiVersion") not in (API_VERSION_K8S, API_VERSION_INLINE):
            raise ValueError(f"Unsupported apiVersion: {manifest.get('apiVersion')!r}")

        if cls is NylResource:
            kind = manifest["kind"]
            module_name = __name__ + "." + kind.lower()
            try:
                module = __import__(module_name, fromlist=[kind])
                subcls: type[NylResource] = getattr(module, kind)
                assert isinstance(subcls, type) and issubclass(cls, NylResource), f"{subcls} is not a NylResource"
            except (ImportError, AttributeError, AssertionError):
                raise ValueError(f"Unsupported resource kind: {kind}")

        else:
            if manifest["kind"] != cls.KIND:
                raise ValueError(f"Expected kind {cls.KIND!r}, got {manifest['kind']!r}")
            subcls = cls

        manifest = Manifest(manifest)
        manifest.pop("apiVersion")
        manifest.pop("kind")

        return cast(Self, deser(manifest, subcls))

    @classmethod
    def maybe_load(cls, manifest: Manifest) -> "Self | None":
        """
        Maybe load the manifest into a NylResource if the `apiVersion` matches. If the resource kind is not supported,
        an error will be raised. If this is called on a subclass of `NylResource`, the subclass's kind will also be
        checked.
        """

        if cls.matches(manifest):
            return cls.load(manifest)
        return None

    @classmethod
    def matches(cls, manifest: Manifest, apiVersion: str | Collection[str] | None = None) -> bool:
        """
        Check if the manifest is a NylResource of the correct `apiVersion` and possibly `kind` (if called on a
        `NylResource` subclass).
        """

        if apiVersion is None:
            apiVersion = {API_VERSION_K8S, API_VERSION_INLINE}
        elif isinstance(apiVersion, str):
            apiVersion = {apiVersion}

        if manifest.get("apiVersion") not in apiVersion:
            return False

        if cls is not NylResource and manifest["kind"] != cls.KIND:
            return False

        return True

    def dump(self) -> Manifest:
        """
        Dump the resource to a manifest.
        """

        manifest = cast(Manifest, ser(self, type(self), settings=[SerializeDefaults(False)]))
        manifest["apiVersion"] = self.API_VERSION
        manifest["kind"] = self.KIND
        return Manifest(manifest)


@dataclass
class ObjectMetadata:
    """
    Kubernetes object metadata.
    """

    name: str
    namespace: str | None = None
    labels: dict[str, str] | None = None
    annotations: dict[str, str] | None = None
