from pathlib import Path
from typing import Iterable

from kubernetes.client.api_client import ApiClient

from nyl.secrets import SecretProvider, SecretValue


class NullSecretsProvider(SecretProvider):
    def init(self, config_file: Path, api_client: ApiClient | None = None) -> None:
        pass

    def keys(self) -> Iterable[str]:
        return []

    def get(self, secret_name: str) -> str:
        raise KeyError(f"No secrets provider configured; cannot retrieve secret '{secret_name}'.")

    def set(self, secret_name: str, value: SecretValue) -> None:
        raise RuntimeError(f"No secrets provider configured; cannot set secret '{secret_name}'")

    def unset(self, secret_name: str) -> None:
        raise RuntimeError(f"No secrets provider configured; cannot unset secret '{secret_name}'")
