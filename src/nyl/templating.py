"""
Implements Nyl's variant of structured templating.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Iterator, TypeVar, cast
from structured_templates import TemplateEngine as _TemplateEngine
from structured_templates.exceptions import TemplateError
from kubernetes.client.api_client import ApiClient

from kubernetes.dynamic.client import DynamicClient
from kubernetes.client.exceptions import ApiException
from nyl.secrets.config import SecretProvider
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
    return obj


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
        create_placeholders: Whether to create placeholders for templates that fail to evaluate due
            to unsatisfied conditions (e.g. lookup errors).
    """

    current: ClassVar["NylTemplateEngine"]

    secrets: SecretProvider
    client: ApiClient
    create_placeholders: bool

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
                    if not isinstance(exc.__cause__, LookupError) or not self.create_placeholders:
                        raise

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

        return Manifests(result)


def _get_resource_slug(api_version: str, kind: str, name: str, max_length: int = 63) -> str:
    suffix = f"{api_version.replace('/', '-').replace('.', '-')}-{kind}"
    return f"{name}-{suffix[:max_length - len(name) - 1]}".lower()
