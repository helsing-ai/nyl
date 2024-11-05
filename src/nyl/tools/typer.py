from typing import Any, TypeVar

from typer import Typer

T = TypeVar("T")


def new_typer(**kwargs: Any) -> Typer:
    return Typer(no_args_is_help=True, pretty_exceptions_enable=False, **kwargs)
