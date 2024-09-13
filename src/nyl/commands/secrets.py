"""
Interact with the secrets providers configured in `nyl-secrets.yaml`.
"""

import json
from pathlib import Path
import sys
from typing import Optional

from loguru import logger
from typer import Option
from nyl.secrets.config import SecretsConfig
from nyl.secrets.sops import SopsFile
from nyl.tools.fs import shorter_path
from nyl.tools.logging import lazy_str
from nyl.tools.typer import new_typer


app = new_typer(name="secrets", help=__doc__)

sops = new_typer(name="sops", help=__doc__)
app.add_typer(sops)


@app.command()
def list() -> None:
    """
    List the keys for all secrets in the provider.
    """

    secrets = SecretsConfig.load()
    for key in secrets.provider.keys():
        print(key)


@app.command()
def get(key: str, pretty: bool = False) -> None:
    """
    Get the value of a secret as JSON.
    """

    secrets = SecretsConfig.load()
    print(json.dumps(secrets.provider.get(key), indent=4 if pretty else None))


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
        if isinstance(secrets.provider, SopsFile):
            file = secrets.provider.path
        else:
            logger.error("no `file` argument was specified and no SOPS file could be detected in your configuration")
            sys.exit(1)

    logger.opt(ansi=True).info("re-encrypting file '<blue>{}</>'", lazy_str(lambda f: str(shorter_path(f)), file))

    if file_type is None:
        if file.suffix in (".yml", ".yaml"):
            file_type = "yaml"
        elif file.suffix in (".json", ".json5"):
            file_type = "json"
        elif file.suffix in (".sh", ".bash", ".env"):
            file_type = "dotenv"
        else:
            logger.error("could not determine SOPS input/output type from filename, specify with the --type option")
            sys.exit(1)

    sops = SopsFile(file)
    sops.load(file_type)
    sops.save(file_type)
