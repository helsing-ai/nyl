from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable
from databind.core import Union
from loguru import logger
from .config import SecretProvider, SecretValue


@Union.register(SecretProvider, name="sops")
@dataclass
class SopsFile(SecretProvider):
    """
    This secrets provider decodes a SOPS-encrypted YAML or JSON file and serves the secrets stored within.

    Nested structures are supported, and the provider maps them to fully qualified keys using dot notation. The
    nested structure can be accessed as well, returning the full structure as a JSON object.
    """

    path: Path
    """
    The path to the SOPS-encrypted file. This path is resolved relative to the configuration file that the
    provider is defined in.
    """

    do_not_use_in_prod_only_for_testing_sops_age_key: str | None = None
    """
    The key to use for the `--age` option of SOPS. This is useful for testing purposes only and should not be used
    in production.
    """

    _cache: SecretValue | None = field(init=False, repr=False, default=None)

    def _load(self) -> SecretValue:
        if self._cache is None:
            logger.info("Loading secrets with Sops from '{}'", self.path)
            env = os.environ.copy()
            if self.do_not_use_in_prod_only_for_testing_sops_age_key:
                env["SOPS_AGE_KEY"] = self.do_not_use_in_prod_only_for_testing_sops_age_key
            try:
                self._cache = json.loads(
                    subprocess.run(
                        ["sops", "--output-type", "json", "--decrypt", str(self.path)],
                        capture_output=True,
                        text=True,
                        check=True,
                        env=env,
                    ).stdout
                )
            except subprocess.CalledProcessError as exc:
                logger.error("Failed to load secrets from '{}'; stderr={}", self.path, exc.stderr)
                raise
        return self._cache

    # SecretProvider

    def init(self, config_file: Path) -> None:
        self.path = (config_file.parent / self.path).absolute()

    def keys(self) -> Iterable[str]:
        stack = [(self._load(), "")]
        while stack:
            value, prefix = stack.pop(0)
            if prefix != "":
                yield prefix
            match value:
                case dict():
                    stack = [
                        (value, f"{prefix}.{key}" if prefix else key) for key, value in sorted(value.items())
                    ] + stack

    def get(self, key: str) -> SecretValue:
        parts = key.split(".")
        value = self._load()
        for idx, part in enumerate(parts):
            if not isinstance(value, dict):
                raise KeyError(".".join(parts[:idx+1]))
            if part not in value:
                raise KeyError(".".join(parts[:idx+1]))
            value = value[part]
        return value
