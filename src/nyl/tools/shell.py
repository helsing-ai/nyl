from collections.abc import Iterable
import shlex


def pretty_cmd(command: Iterable[str]) -> str:
    return " ".join(map(shlex.quote, command))
