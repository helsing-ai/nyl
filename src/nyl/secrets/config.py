from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable
from pathlib import Path
from databind.core import Union
from loguru import logger

from nyl.tools.fs import find_config_file
from nyl.tools.loads import loadf

SecretValue = dict[str, Any] | list[Any] | str | int | float | bool | None
"""
A secret is a JSON-serializable value that can be stored in a secret provider.
"""


@Union(style=Union.FLAT, discriminator_key="provider")
@dataclass
class SecretProvider(ABC):
    """
    A SecretProvider is a source of secrets that can be accessed by keys.
    """

    @abstractmethod
    def init(self, config_file: Path) -> None:
        """
        Called after loading the provider configuration from a configuration file. The file's path is provided to
        allow the provider to resolve relative paths.
        """

    @abstractmethod
    def keys(self) -> Iterable[str]:
        """
        Return an iterator over all keys in the provider.
        """

    @abstractmethod
    def get(self, key: str) -> SecretValue:
        """
        Retrieve a secret by key.

        Args:
            key: The key of the secret to retrieve.
        Returns:
            The secret value.
        Raises:
            KeyError: If the key does not exist.
        """


@dataclass
class SecretsConfig:
    FILENAMES = ["nyl-secrets.yaml", "nyl-secrets.toml", "nyl-secrets.json"]

    file: Path | None
    provider: SecretProvider

    @staticmethod
    def load(file: Path | None = None, /) -> "SecretsConfig":
        """
        Load the secrets configuration from the given or the default configuration file. If the configuration file does
        not exist, a [NullSecretsProvider] is used.
        """

        from databind.json import load as deser
        from nyl.secrets.null import NullSecretsProvider

        if file is None:
            file = find_config_file(SecretsConfig.FILENAMES, required=False)
        if file is None:
            logger.debug("Found no Nyl secrets configuration file.")
            return SecretsConfig(None, NullSecretsProvider())
        else:
            logger.debug("Loading secrets configuration from '{}'.", file)
            provider = deser(loadf(file), SecretProvider, filename=str(file))
            provider.init(file)
            return SecretsConfig(file, provider)
