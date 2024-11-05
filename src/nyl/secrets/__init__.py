from abc import ABC, abstractmethod
from typing import Any, Iterable
from pathlib import Path
from databind.core import Union
from dataclasses import dataclass


SecretValue = dict[str, Any] | list[Any] | str | int | float | bool | None
"""
A secret is a JSON-serializable value that can be stored in a secret provider.
"""


@Union(style=Union.FLAT, discriminator_key="type")
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
    def get(self, key: str, /) -> SecretValue:
        """
        Retrieve a secret by key.

        Args:
            key: The key of the secret to retrieve.
        Returns:
            The secret value.
        Raises:
            KeyError: If the key does not exist.
        """

    @abstractmethod
    def set(self, key: str, value: SecretValue, /) -> None:
        """
        Set the value of a key.

        Args:
            key: The key of the secret to set.
        Raises:
            KeyError: If the key is invalid.
            ValueError: If the value is invalid.
            RuntimeError: If the key cannot be set for systematic reasons.
        """

    def unset(self, key: str, /) -> None:
        """
        Unset a secret by its key.

        Args:
            key: The key of the secret to unset.
        """


from . import config, sops  # noqa
