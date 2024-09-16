"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

import json

from typer import Option
from nyl.secrets.config import SecretsConfig
from nyl.tools.typer import new_typer


app = new_typer(name="secrets", help=__doc__)

# Initialized from callback for access by subcommands.
provider: str


@app.callback()
def callback(
    _provider: str = Option(
        "default",
        "--provider",
        help="The name of the configured secrets provider to use.",
        envvar="NYL_SECRETS",
    ),
) -> None:
    """
    Interact with the secrets providers configured in `nyl-secrets.yaml`.
    """

    global provider
    provider = _provider


@app.command()
def list(
    providers: bool = Option(
        False, help="List the configured secrets providers instead of the current provider's available keys."
    ),
) -> None:
    """
    List the keys for all secrets in the provider.
    """

    secrets = SecretsConfig.load()
    if providers:
        for alias, impl in secrets.providers.items():
            print(alias, impl)
    else:
        for key in secrets.providers[provider].keys():
            print(key)


@app.command()
def get(key: str, pretty: bool = False) -> None:
    """
    Get the value of a secret as JSON.
    """

    secrets = SecretsConfig.load()
    print(json.dumps(secrets.providers[provider].get(key), indent=4 if pretty else None))
