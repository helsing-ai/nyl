"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

import json
from pathlib import Path
from shlex import quote
import sys
from typing import Optional

from loguru import logger
from typer import Option
from nyl.secrets.config import SecretsConfig
from nyl.secrets.sops import SopsFile, detect_sops_format
from nyl.tools.fs import shorter_path
from nyl.tools.logging import lazy_str
from nyl.tools.typer import new_typer


app = new_typer(name="secrets", help=__doc__)

sops = new_typer(name="sops", help=__doc__)
app.add_typer(sops)

# Initialized from callback for access by subcommands.
provider: str


@app.callback()
def callback(
    _provider: str = Option(
        "default", "--provider", help="The name of the configured secrets provider to use.", envvar="NYL_SECRETS"
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


@sops.command()
def re_encrypt(
    file: Optional[Path] = Option(
        None,
        help="The SOPS-file to re-encrypt. Defaults to the SOPS file mentioned in `nyl-secrets.yaml` "
        "(when using the `sops` provider).",
    ),
    file_type: Optional[str] = Option(
        None, "--type", help="The SOPS input/output type if it cannot be determined from the file name."
    ),
) -> None:
    """
    Re-encrypt a SOPS file.

    This should be used after updating the public keys in the `.sops.yaml` configuration to ensure that the SOPS file
    is encrypted for all the specified keys.

    Note that you need to be able to decrypt the SOPS file to re-encrypt it (duh).
    """

    if file is None:
        secrets = SecretsConfig.load()
        if isinstance(impl := secrets.providers[provider], SopsFile):
            file = impl.path
        else:
            logger.error("no `file` argument was specified and no SOPS file could be detected in your configuration")
            sys.exit(1)

    logger.opt(ansi=True).info("re-encrypting file '<blue>{}</>'", lazy_str(lambda f: str(shorter_path(f)), file))

    if file_type is None:
        file_type = detect_sops_format(file.suffix)
        if not file_type:
            logger.error("could not determine SOPS input/output type from filename, specify with the --type option")
            sys.exit(1)

    sops = SopsFile(file)
    sops.load(file_type)
    sops.save(file_type)


@sops.command()
def export_dotenv(
    file: Path,
    prefix: str = Option("", help="Only export keys with the given prefix, and strip the prefix."),
    file_type: Optional[str] = Option(
        None, "--type", help="The SOPS input type if it cannot be determined from the file name."
    ),
) -> None:
    """
    A utility function to export key-value pairs from a SOPS file in dotenv format. This is useful for exporting
    environment variables from a SOPS file, e.g. using Direnv.

    Note that only string values are exported.
    """

    if file_type is None:
        file_type = detect_sops_format(file.suffix)
        if not file_type:
            logger.error("could not determine SOPS input type from filename, specify with the --type option")
            sys.exit(1)

    sops = SopsFile(file)
    sops.load(file_type)

    for key in sops.keys():
        if not key.startswith(prefix):
            continue
        value = sops.get(key)
        if isinstance(value, str):
            print(f"export {key[len(prefix):]}={quote(value)}")
