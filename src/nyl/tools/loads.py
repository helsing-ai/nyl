"""Utility to loading file contents from various formats (JSON, YAML, TOML)."""

from importlib import import_module
from pathlib import Path
from typing import IO, Any, AnyStr

loads_functions = {
    "json": "json:loads",
    "toml": "tomllib:loads",
    "yaml": "yaml:safe_load",
    "yml": "yaml:safe_load",
}

load_functions = {
    "json": "json:load",
    "toml": "tomllib:load",
    "yaml": "yaml:safe_load",
    "yml": "yaml:safe_load",
}


def loads(format: str, data: str) -> Any:
    module_name, function_name = loads_functions[format].split(":")
    func = getattr(import_module(module_name), function_name)
    return func(data)


def load(format: str, fp: IO[AnyStr]) -> Any:
    module_name, function_name = load_functions[format].split(":")
    func = getattr(import_module(module_name), function_name)
    return func(fp)


def loadf(file: str | Path, format: str | None = None) -> Any:
    file = Path(file)
    if format is None:
        format = file.suffix.lstrip(".")
    with file.open("rb") as fp:
        return load(format, fp)
