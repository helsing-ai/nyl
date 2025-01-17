import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from databind.core import Union
from loguru import logger

from nyl.secrets import SecretProvider, SecretValue
from nyl.tools.di import DependenciesProvider
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd


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

    do_not_use_in_prod_only_for_testing_sops_age_key: str | None = field(default=None, repr=False)
    """
    The key to use for the `--age` option of SOPS. This is useful for testing purposes only and should not be used
    in production.
    """

    _cache: SecretValue | None = field(init=False, repr=False, default=None)

    def _getenv(self) -> Mapping[str, str]:
        if self.do_not_use_in_prod_only_for_testing_sops_age_key:
            env = os.environ.copy()
            env["SOPS_AGE_KEY"] = self.do_not_use_in_prod_only_for_testing_sops_age_key
            return env
        else:
            return os.environ

    def _key2sops(self, key: str) -> str:
        """
        Convert a dotted key to a key that SOPS understands for setting/unsetting.
        """

        # Convert the key to one that SOPS understands.
        # TODO: Support integer indexing?
        sops_key = ""
        for part in key.split("."):
            sops_key += f'["{part}"]'
        return sops_key

    def load(self, input_type: str | None = None) -> SecretValue:
        if self._cache is None:
            logger.info("Loading secrets with Sops from '{}'", self.path)
            command = ["sops", "--output-type", "json", "--decrypt"]
            if input_type is not None:
                command += ["--input-type", input_type]
            command.append(str(self.path))
            logger.opt(colors=True).debug("Running command $ <yellow>{}</>", lazy_str(pretty_cmd, command))
            try:
                self._cache = json.loads(
                    subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        check=True,
                        env=self._getenv(),
                    ).stdout
                )
            except subprocess.CalledProcessError as exc:
                logger.error("Failed to load secrets from '{}'; stderr={}", self.path, exc.stderr)
                raise
        return self._cache

    def save(self, output_type: str) -> None:
        command = ["sops", "--output-type", output_type, "--input-type", "json", "--encrypt", "/dev/stdin"]
        logger.opt(colors=True).debug("Running command $ <yellow>{}</>", lazy_str(pretty_cmd, command))
        output = subprocess.run(
            command,
            text=True,
            capture_output=True,
            input=json.dumps(self._cache),
            check=True,
            env=self._getenv(),
        ).stdout
        self.path.write_text(output)

    # SecretProvider

    def init(self, config_file: Path, dependencies: DependenciesProvider) -> None:
        self.path = (config_file.parent / self.path).absolute()

    def keys(self) -> Iterable[str]:
        stack = [(self.load(), "")]
        while stack:
            value, prefix = stack.pop(0)
            if prefix != "":
                yield prefix
            match value:
                case dict():
                    stack = [
                        (value, f"{prefix}.{key}" if prefix else key) for key, value in sorted(value.items())
                    ] + stack

    def get(self, key: str, /) -> SecretValue:
        parts = key.split(".")
        value = self.load()
        for idx, part in enumerate(parts):
            if not isinstance(value, dict):
                raise KeyError(".".join(parts[: idx + 1]))
            if part not in value:
                raise KeyError(".".join(parts[: idx + 1]))
            value = value[part]
        return value

    def set(self, key: str, value: SecretValue, /) -> None:
        sops_key = self._key2sops(key)
        command = ["sops", "set", str(self.path), sops_key, json.dumps(value)]
        safe_command = ["sops", "set", str(self.path), sops_key, "MASKED"]
        logger.opt(colors=True).debug("Running command $ <yellow>{}</>", lazy_str(pretty_cmd, safe_command))
        subprocess.run(command, env=self._getenv(), check=True)

    def unset(self, key: str, /) -> None:
        sops_key = self._key2sops(key)
        command = ["sops", "unset", str(self.path), sops_key]
        logger.opt(colors=True).debug("Running command $ <yellow>{}</>", lazy_str(pretty_cmd, command))
        try:
            subprocess.run(command, env=self._getenv(), text=True, capture_output=True, check=True)
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1 and "Key not found" in exc.stderr:
                logger.warning("Key '{}' not found in SOPS file '{}'", key, self.path)
            else:
                raise


def detect_sops_format(suffix: str) -> str | None:
    """
    Tells the SOPS file format based on the file suffix. Never returns "binary".
    Returns `None` if the format cannot be determined.
    """

    suffix = suffix.removeprefix(".")
    if suffix in ("yml", "yaml"):
        return "yaml"
    elif suffix in ("json", "json5"):
        return "json"
    elif suffix in ("sh", "bash", "env"):
        return "dotenv"
    else:
        return None
