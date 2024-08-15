"""
Helper commands for the ArgoCD integration.
"""

import sys

from loguru import logger
from nyl.project.config import ProjectConfig
from nyl.secrets.config import SecretsConfig
from nyl.tools.typer import new_typer


app = new_typer(name="argocd", help=__doc__)


@app.command()
def discovery() -> None:
    """
    Discover whether the current working directory uses Nyl. This is when either a `nyl-project.yaml` or
    `nyl-secrets.yaml` file is present in the directory or any of its parent directories.
    """

    found = False
    if (file := ProjectConfig.load().file) is not None:
        print(file.absolute())
        found = True
    if (file := SecretsConfig.load().file) is not None:
        print(file.absolute())
        found = True

    if not found:
        logger.info("No Nyl project or secrets configuration found.")
    else:
        logger.info("Found Nyl project and/or secrets configuration.")
    sys.exit(0 if found else 1)
