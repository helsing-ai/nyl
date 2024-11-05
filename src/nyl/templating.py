"""
Implements Nyl's variant of structured templating.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Iterator, Literal, Sequence, TypeVar, cast

from loguru import logger
from structured_templates import TemplateEngine as _TemplateEngine
from structured_templates.exceptions import TemplateError

from kubernetes.client.api_client import ApiClient
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.client import DynamicClient
from kubernetes.dynamic.resource import ResourceField, ResourceInstance
from nyl.secrets import SecretProvider
from nyl.tools.types import Manifest, Manifests

T_Callable = TypeVar("T_Callable", bound=Callable[..., Any])
registered_functions: dict[str, Callable[..., Any]] = {}
RESERVED_NAMES = {"secrets"}


def register(name: str | None = None) -> Callable[[T_Callable], T_Callable]:
    """
    Register a global function for use in structured templates.
    """

    def decorator(func: T_Callable) -> T_Callable:
        nonlocal name
        name = name or func.__name__
        if name in RESERVED_NAMES:
            raise ValueError(f"Cannot register function with reserved name '{name}'.")
        registered_functions[name] = func
        return func

    return decorator


@register()
def random_password(length: int = 32) -> str:
    """
    Generate a random password.
    """

    import secrets

    return secrets.token_urlsafe(length)


@register()
def bcrypt(password: str) -> str:
    """
    Hash a password using bcrypt.
    """

    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@register()
def b64decode(data: str) -> str:
    """
    Decode base64 data and then from UTF-8.
    """

    import base64

    return base64.b64decode(data).decode("utf-8")


@register()
def b64encode(data: str) -> str:
    """
    Encode data to base64 from UTF-8 and then to ASCII.
    """

    import base64

    return base64.b64encode(data.encode("utf-8")).decode("ascii")


@register()
def lookup(api_version: str, kind: str, name: str, namespace: str) -> Any:
    client = NylTemplateEngine.current.dynamic_client
    resource = client.resources.get(api_version=api_version, kind=kind)
    try:
        obj = resource.get(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise LookupError(f"Resource '{kind}/{name}' not found in namespace '{namespace}'.")
        else:
            raise
    return LookupResourceWrapper(obj)


class LookupResourceWrapper(Mapping[str, Any]):
    """
    A wrapper for a Kubernetes resources returned by `lookup()` that permits looking up fields by `__getitem__()`
    and `__getattr__()`. This wraps a `ResourceInstance` or `ResourceField`, which can later be treated by the
    `NylTemplateEngine` to serialize into a dictionary when embedded into a manifest.

    This class is needed because the YAML serializer will not be able to serialize the `ResourceInstance` or
    `ResourceField` objects returned by `lookup()`.
    """

    @staticmethod
    def maybe_wrap(obj: Any) -> Any:
        if isinstance(obj, (ResourceInstance, ResourceField)):
            return LookupResourceWrapper(obj)
        if isinstance(obj, Sequence) and not isinstance(obj, str):
            obj = [LookupResourceWrapper.maybe_wrap(x) for x in obj]
        return obj

    @staticmethod
    def materialize(obj: Any) -> Any:
        match obj:
            case LookupResourceWrapper():
                return obj.__obj.to_dict()
            case str():
                return obj
        if isinstance(obj, Sequence):
            return [LookupResourceWrapper.materialize(x) for x in obj]
        if isinstance(obj, Mapping):
            return {k: LookupResourceWrapper.materialize(v) for k, v in obj.items()}
        return obj

    def __init__(self, obj: ResourceInstance | ResourceField) -> None:
        assert isinstance(obj, (ResourceInstance, ResourceField)), f"got {type(obj).__name__}"
        self.__obj = obj

    def __iter__(self) -> Iterator[str]:
        if isinstance(self.__obj, ResourceInstance):
            target = self.__obj.attributes
        else:
            target = self.__obj
        for key, _ in target:
            yield key

    def __len__(self) -> int:
        # TODO: Find a better (faster) way to get the length of the resource instance/field attributes.
        return len(self.__obj.to_dict())

    def __getattr__(self, key: str) -> Any:
        return LookupResourceWrapper.maybe_wrap(getattr(self.__obj, key))

    def __getitem__(self, key: str) -> Any:
        return LookupResourceWrapper.maybe_wrap(self.__obj[key])


class LookupError(Exception):
    """
    Raised when a `lookup()` call fails because the resource was not found.
    """


@dataclass
class NylTemplateEngine:
    """
    Nyl's structured template engine.

    Args:
        secrets: The secrets engine to make available to templated expressions.
        client: The Kubernetes API client to use for lookups.
        on_lookup_failure: What should happen on failure to perform lookups of other Kubernetes resources.
    """

    current: ClassVar["NylTemplateEngine"]

    secrets: SecretProvider
    client: ApiClient
    on_lookup_failure: Literal["Error", "CreatePlaceholder", "SkipResource"] = "Error"

    def __post_init__(self) -> None:
        self.dynamic_client = DynamicClient(self.client)

    @contextmanager
    def as_current(self) -> Iterator["NylTemplateEngine"]:
        """
        Set this template engine as the current one.
        """

        prev = getattr(NylTemplateEngine, "current", None)
        NylTemplateEngine.current = self
        try:
            yield self
        finally:
            if prev is None:
                del NylTemplateEngine.current
            else:
                NylTemplateEngine.current = prev

    def _new_engine(self) -> _TemplateEngine:
        return _TemplateEngine({"secrets": self.secrets, **registered_functions})

    def evaluate(self, value: Manifests, recursive: bool = True) -> Manifests:
        result = []
        with self.as_current():
            for item in value:
                try:
                    result.append(cast(Manifest, self._new_engine().evaluate(item, recursive)))
                except TemplateError as exc:
                    if isinstance(exc.__cause__, LookupError):
                        if self.on_lookup_failure == "CreatePlaceholder":
                            result.append(
                                Manifest(
                                    {
                                        "apiVersion": "nyl.io/v1",
                                        "kind": "Placeholder",
                                        "metadata": {
                                            "name": _get_resource_slug(
                                                item["apiVersion"], item["kind"], item["metadata"]["name"]
                                            ),
                                            "namespace": item["metadata"].get("namespace"),
                                        },
                                        "spec": {"reason": "LookupError", "message": str(exc.__cause__)},
                                    }
                                )
                            )
                            continue
                        elif self.on_lookup_failure == "SkipResource":
                            # TODO: More/clearer information on which resource is being skipped and why.
                            logger.warning("Failed lookup(), skipping resource\n\n{}", exc)
                            continue
                    raise

        result = LookupResourceWrapper.materialize(result)
        return Manifests(result)


def _get_resource_slug(api_version: str, kind: str, name: str, max_length: int = 63) -> str:
    suffix = f"{api_version.replace('/', '-').replace('.', '-')}-{kind}"
    return f"{name}-{suffix[:max_length - len(name) - 1]}".lower()
