"""
Implements Nyl's variant of structured templating.
"""

from typing import Any, Callable, TypeVar
from structured_templates import TemplateEngine as _TemplateEngine

from nyl.secrets.config import SecretProvider

T_Callable = TypeVar("T_Callable", bound=Callable)
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


class NylTemplateEngine(_TemplateEngine):
    """
    Nyl's structured template engine.
    """

    def __init__(self, secrets: SecretProvider) -> None:
        super().__init__({"secrets": secrets, **registered_functions})
