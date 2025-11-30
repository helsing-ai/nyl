"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

import json
import json as _json

from loguru import logger
from typer import Option, Typer

from nyl.core import DIContainer, setup_base_container
from nyl.secrets import SecretProvider
from nyl.secrets.config import SecretsConfig
from nyl.tools.typer import new_typer

app: Typer = new_typer(name="secrets", help=__doc__)

# Module-level container shared between callback and commands
_container: DIContainer | None = None
_current_provider_name: str | None = None


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

    global _container, _current_provider_name

    _container = DIContainer()
    setup_base_container(_container, profile=profile)
    _current_provider_name = provider

    # Register the current provider
    def _get_current_provider() -> SecretProvider:
        assert _container is not None
        secrets_config = _container.resolve(SecretsConfig)
        return secrets_config.providers[provider]

    _container.register_factory(SecretProvider, _get_current_provider)  # type: ignore[type-abstract]


@app.command()
def list(
    providers: bool = Option(
        False, help="List the configured secrets providers instead of the current provider's available keys."
    ),
) -> None:
    """
    List the keys for all secrets in the provider.
    """

    assert _container is not None, "Container not initialized"

    if providers:
        for alias, impl in _container.resolve(SecretsConfig).providers.items():
            print(alias, impl)
    else:
        for key in _container.resolve(SecretProvider).keys():  # type: ignore[type-abstract]
            print(key)


@app.command()
def get(key: str, pretty: bool = False, raw: bool = False) -> None:
    """
    Get the value of a secret as JSON.
    """

    assert _container is not None, "Container not initialized"

    value = _container.resolve(SecretProvider).get(key)  # type: ignore[type-abstract]
    if raw and isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=4 if pretty else None))


@app.command()
def set(key: str, value: str, json: bool = False) -> None:
    """
    Set the value of a secret.
    """

    assert _container is not None, "Container not initialized"
    assert _current_provider_name is not None, "Provider name not set"

    secrets = _container.resolve(SecretProvider)  # type: ignore[type-abstract]
    logger.info("Setting key '{}' in provider '{}'", key, _current_provider_name)
    secrets.set(key, _json.loads(value) if json else value)


@app.command()
def unset(key: str) -> None:
    """
    Unset the value of a secret.
    """

    assert _container is not None, "Container not initialized"
    assert _current_provider_name is not None, "Provider name not set"

    secrets = _container.resolve(SecretProvider)  # type: ignore[type-abstract]
    logger.info("Unsetting key '{}' in provider '{}'", key, _current_provider_name)
    secrets.unset(key)
