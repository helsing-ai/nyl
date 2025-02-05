from collections.abc import Iterator
from typing import Any, TextIO

import yaml
from yaml import SafeDumper, SafeLoader


class PatchedSafeLoader(SafeLoader):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # See https://github.com/yaml/pyyaml/issues/89
        super().__init__(*args, **kwargs)
        self.yaml_implicit_resolvers = self.yaml_implicit_resolvers.copy()
        self.yaml_implicit_resolvers.pop("=")


class PatchedSafeDumper(SafeDumper):
    pass


def dumps(data: Any) -> str:
    return yaml.dump(data, Dumper=PatchedSafeDumper)


def loads(text: str) -> Any:
    return yaml.load(text, Loader=PatchedSafeLoader)


def loads_all(stream: str | TextIO) -> Iterator[Any]:
    return yaml.load_all(stream, Loader=PatchedSafeLoader)
