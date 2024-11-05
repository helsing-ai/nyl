from collections.abc import Callable
from typing import ParamSpec

P = ParamSpec("P")


class lazy_str:
    def __init__(self, callable: Callable[P, str], *args: P.args, **kwargs: P.kwargs) -> None:
        self.callable = callable
        self.args = args
        self.kwargs = kwargs

    def __str__(self) -> str:
        return self.callable(*self.args, **self.kwargs)

    def __repr__(self) -> str:
        return f"lazy_str({self.callable!r}, *{self.args!r}, **{self.kwargs!r})"
