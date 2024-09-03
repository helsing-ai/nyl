"""
Implements Nyl's variant of structured templating.
"""

from contextlib import contextmanager
from typing import Any, Callable, ClassVar, Iterator, TypeVar
from structured_templates import TemplateEngine as _TemplateEngine
from kubernetes.client.api_client import ApiClient
from structured_templates.context import Context

from kubernetes.dynamic.client import DynamicClient
from nyl.secrets.config import SecretProvider

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
    obj = resource.get(name=name, namespace=namespace)
    return obj


class NylTemplateEngine(_TemplateEngine):
    """
    Nyl's structured template engine.
    """

    current: ClassVar["NylTemplateEngine"]

    def __init__(self, secrets: SecretProvider, client: ApiClient) -> None:
        super().__init__({"secrets": secrets, **registered_functions})
        self.client = client
        self.dynamic_client = DynamicClient(client)

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

    # TemplateEngine

    def evaluate(
        self,
        value: dict[str, Any]
        | list[Any]
        | str
        | int
        | float
        | bool
        | None
        | Context[dict[str, Any] | list[Any] | str | int | float | bool | None],
        recursive: bool = True,
    ) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
        with self.as_current():
            return super().evaluate(value, recursive)
