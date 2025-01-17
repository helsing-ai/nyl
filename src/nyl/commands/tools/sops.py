"""
Utilities for SOPS files.
"""

import sys
from pathlib import Path
from shlex import quote
from typing import Optional

from loguru import logger
from typer import Option, Typer

from nyl.commands import PROVIDER
from nyl.secrets.config import SecretsConfig
from nyl.secrets.sops import SopsFile, detect_sops_format
from nyl.tools.fs import shorter_path
from nyl.tools.logging import lazy_str
from nyl.tools.typer import new_typer

app: Typer = new_typer(name="sops", help=__doc__)


@app.command()
def re_encrypt(
    provider: str = Option(
        "default",
        "--provider",
        help="The name of the configured secrets provider to use.",
        envvar="NYL_SECRETS",
    ),
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
        secrets = PROVIDER.get(SecretsConfig)
        if isinstance(impl := secrets.providers[provider], SopsFile):
            file = impl.path
        else:
            logger.error("no `file` argument was specified and no SOPS file could be detected in your configuration")
            sys.exit(1)

    logger.opt(colors=True).info("re-encrypting file '<blue>{}</>'", lazy_str(lambda f: str(shorter_path(f)), file))

    if file_type is None:
        file_type = detect_sops_format(file.suffix)
        if not file_type:
            logger.error("could not determine SOPS input/output type from filename, specify with the --type option")
            sys.exit(1)

    sops = SopsFile(file)
    sops.load(file_type)
    sops.save(file_type)


@app.command()
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
