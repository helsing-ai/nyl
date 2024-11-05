"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

from dataclasses import dataclass
import json
import json as _json

from loguru import logger
from typer import Option
from nyl.secrets.config import SecretsConfig
from nyl.tools.typer import new_typer
from nyl.commands import ApiClientConfig, PROVIDER


app = new_typer(name="secrets", help=__doc__)


@dataclass
class SelectedProviderName:
    "Stores the name of the provider selected in the `nyl secrets` command."

    value: str


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

    PROVIDER.set(SelectedProviderName, SelectedProviderName(provider))
    PROVIDER.set(ApiClientConfig, ApiClientConfig(in_cluster=False, profile=profile))


@app.command()
def list(
    providers: bool = Option(
        False, help="List the configured secrets providers instead of the current provider's available keys."
    ),
) -> None:
    """
    List the keys for all secrets in the provider.
    """

    secrets = PROVIDER.get(SecretsConfig)
    if providers:
        for alias, impl in secrets.providers.items():
            print(alias, impl)
    else:
        provider = PROVIDER.get(SelectedProviderName).value
        for key in secrets.providers[provider].keys():
            print(key)


@app.command()
def get(key: str, pretty: bool = False) -> None:
    """
    Get the value of a secret as JSON.
    """

    secrets = PROVIDER.get(SecretsConfig)
    provider = PROVIDER.get(SelectedProviderName).value
    print(json.dumps(secrets.providers[provider].get(key), indent=4 if pretty else None))


@app.command()
def set(key: str, value: str, json: bool = False) -> None:
    """
    Set the value of a secret.
    """

    provider = PROVIDER.get(SelectedProviderName).value
    logger.info("Setting key '{}' in provider '{}'", key, provider)
    secrets = PROVIDER.get(SecretsConfig)
    secrets.providers[provider].set(key, _json.loads(value) if json else value)


@app.command()
def unset(key: str) -> None:
    """
    Unset the value of a secret.
    """

    provider = PROVIDER.get(SelectedProviderName).value
    logger.info("Unsetting key '{}' in provider '{}'", key, provider)
    secrets = PROVIDER.get(SecretsConfig)
    secrets.providers[provider].unset(key)
