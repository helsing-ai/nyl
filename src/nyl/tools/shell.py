import shlex
from collections.abc import Iterable


def pretty_cmd(command: Iterable[str]) -> str:
    return " ".join(map(shlex.quote, command))
