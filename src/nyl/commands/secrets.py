"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

import json
import json as _json

from loguru import logger
from typer import Option, Typer

from nyl.commands import PROVIDER, ApiClientConfig
from nyl.secrets import SecretProvider
from nyl.secrets.config import SecretsConfig
from nyl.tools.typer import new_typer

app: Typer = new_typer(name="secrets", help=__doc__)


@app.callback()
def callback(
    provider: str = Option(
        "default",
        "--provider",
        help="The name of the configured secrets provider to use.",
        envvar="NYL_SECRETS",
    ),
    profile: str | None = Option(
        None,
        "--profile",
        help="The Nyl profile to assume.",
        envvar="NYL_PROFILE",
    ),
) -> None:
    """
    Interact with the secrets providers configured in `nyl-secrets.yaml`.
    """

    PROVIDER.set(ApiClientConfig, ApiClientConfig(in_cluster=False, profile=profile))
    PROVIDER.set_lazy(tuple[str, SecretProvider], lambda: (provider, PROVIDER.get(SecretsConfig).providers[provider]))
    PROVIDER.set_lazy(SecretProvider, lambda: PROVIDER.get(tuple[str, SecretProvider])[1])  # type: ignore[type-abstract]


@app.command()
def list(
    providers: bool = Option(
        False, help="List the configured secrets providers instead of the current provider's available keys."
    ),
) -> None:
    """
    List the keys for all secrets in the provider.
    """

    if providers:
        for alias, impl in PROVIDER.get(SecretsConfig).providers.items():
            print(alias, impl)
    else:
        for key in PROVIDER.get(SecretProvider).keys():  # type: ignore[type-abstract]
            print(key)


@app.command()
def get(key: str, pretty: bool = False, raw: bool = False) -> None:
    """
    Get the value of a secret as JSON.
    """

    value = PROVIDER.get(SecretProvider).get(key)  # type: ignore[type-abstract]
    if raw and isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=4 if pretty else None))


@app.command()
def set(key: str, value: str, json: bool = False) -> None:
    """
    Set the value of a secret.
    """

    provider_name, secrets = PROVIDER.get(tuple[str, SecretProvider])
    logger.info("Setting key '{}' in provider '{}'", key, provider_name)
    secrets.set(key, _json.loads(value) if json else value)


@app.command()
def unset(key: str) -> None:
    """
    Unset the value of a secret.
    """

    provider_name, secrets = PROVIDER.get(tuple[str, SecretProvider])
    logger.info("Unsetting key '{}' in provider '{}'", key, provider_name)
    secrets.unset(key)
