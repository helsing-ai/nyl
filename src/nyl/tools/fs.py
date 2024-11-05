import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, overload


@overload
def find_config_file(
    filename: str | Sequence[str], cwd: Path | None = None, required: Literal[False] = False
) -> Path | None: ...


@overload
def find_config_file(
    filename: str | Sequence[str], cwd: Path | None = None, required: Literal[True] = True
) -> Path: ...


def find_config_file(filename: str | Sequence[str], cwd: Path | None = None, required: bool = True) -> Path | None:
    """
    Find a file with the given *filename* in the given *cwd* or any of its parent directories.
    """

    if isinstance(filename, str):
        filename = [filename]

    if cwd is None:
        cwd = Path.cwd()

    for directory in [cwd] + list(cwd.parents):
        for file in map(lambda name: directory / name, filename):
            if file.exists():
                return file

    if required:
        raise FileNotFoundError(f"Could not find '{filename}' in '{Path.cwd()}' or any of its parent directories.")

    return None


def shorter_path(path: Path, cwd: Path | None = None) -> Path:
    """Returns the relative path if it's shorter."""

    new_path = Path(os.path.relpath(path, cwd or Path.cwd()))
    if len(str(new_path)) < len(str(path)):
        return new_path
    return path


def distance_to_cwd(path: Path, cwd: Path | None = None) -> int:
    """
    Returns the dinstance of *path* to the current working directory.

    If *path* is a subdirectory of *cwd*, the distance is positive. Otherwise, it's negative. If *path* is not a
    subdirectory of *cwd*, a ValueError is raised.
    """

    cwd = cwd or Path.cwd()

    sign = 1
    if not path.is_relative_to(cwd):
        if not cwd.is_relative_to(path):
            raise ValueError(f"Path '{path}' is not relative to '{cwd}'")
        path, cwd = cwd, path
        sign = -1

    return len(path.relative_to(cwd).parts) * sign
