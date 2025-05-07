"""
Nyl is a flexible configuration management tool for Kubernetes resources that can be used to generate and deploy
applications directly or integrate as an ArgoCD ConfigManagementPlugin.
"""

import json
import os
import shlex
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger
from typer import Option, Typer

from kubernetes.client.api_client import ApiClient
from nyl import __version__
from nyl.profiles import ProfileManager
from nyl.project.config import ProjectConfig
from nyl.secrets.config import SecretsConfig
from nyl.tools.di import DependenciesProvider
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd
from nyl.tools.typer import new_typer

app: Typer = new_typer(help=__doc__)

# A global instance that we use for dependency injection.
PROVIDER = DependenciesProvider.default()

LOG_TIME_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
LOG_LEVEL_FORAMT = "<level>{level: <8}</level>"
LOG_DETAILS_FORMAT = "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
LOG_MESSAGE_FORMAT = "<level>{message}</level>"


class LogLevel(str, Enum):
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Retrieving the Kubernetes API client depends on whether in-cluster configuration should be used or not.
@dataclass(kw_only=True)
class ApiClientConfig:
    in_cluster: bool
    " Load the in-cluster configuration if enabled; forego any Nyl profile configuration. "
    profile: str | None
    " If not loading the in-cluster configuration, use the given Nyl profile. Otherwise, use the default kubeconfig. "


@app.callback()
def _callback(
    quiet: bool = Option(False, "--quiet", "-q", help="Shortcut for --log-level=error."),
    log_level: LogLevel = Option(
        LogLevel.INFO,
        "--log-level",
        "-l",
        help="The log level to use.",
        envvar="NYL_LOG_LEVEL",
    ),
    log_details: bool = Option(False, help="Include logger- and function names in the log message format."),
    log_file: Optional[Path] = Option(None, help="Additionally log to the given file."),
) -> None:
    if log_details:
        fmt = f"{LOG_TIME_FORMAT} | {LOG_LEVEL_FORAMT} | {LOG_DETAILS_FORMAT} | {LOG_MESSAGE_FORMAT}"
    else:
        fmt = f"{LOG_TIME_FORMAT} | {LOG_LEVEL_FORAMT} | {LOG_MESSAGE_FORMAT}"

    logger.remove()
    logger.level("METRIC", 40, "<green><bold>")
    logger.add(sys.stderr, level=LogLevel.ERROR.name if quiet else log_level.name, format=fmt)
    if log_file:
        logger.add(log_file, level=log_level.name, format=fmt)
    logger.opt(colors=True).debug("Nyl v{} run from <yellow>{}</>.", __version__, Path.cwd())

    # Log some helpful information for debugging purposes.
    logger.debug("Used command-line arguments: {}", lazy_str(pretty_cmd, sys.argv))
    logger.debug("Current working directory: {}", Path.cwd())
    log_env = {}
    for key, value in os.environ.items():
        if key.startswith("ARGOCD_") or key.startswith("NYL_") or key.startswith("KUBE_"):
            log_env[key] = value
    logger.debug("Nyl-relevant environment variables: {}", lazy_str(json.dumps, log_env, indent=2))

    PROVIDER.set_lazy(ProfileManager, lambda: ProfileManager.load(required=False))
    PROVIDER.set_lazy(SecretsConfig, lambda: SecretsConfig.load(dependencies=PROVIDER))
    PROVIDER.set_lazy(ProjectConfig, lambda: ProjectConfig.load(dependencies=PROVIDER))
    PROVIDER.set_lazy(
        ApiClient,
        lambda: template.get_incluster_kubernetes_client()
        if PROVIDER.get(ApiClientConfig).in_cluster
        else template.get_profile_kubernetes_client(
            PROVIDER.get(ProfileManager), PROVIDER.get(ApiClientConfig).profile
        ),
    )


@app.command()
def version() -> None:
    """
    Print the version of Nyl.
    """

    print(f"Nyl v{__version__}")
    sys.exit(0)


from . import add  # noqa: E402
from . import crds  # noqa: F401,E402
from . import new  # noqa: E402
from . import profile  # noqa: E402
from . import run  # noqa: F401, E402
from . import secrets  # noqa: E402
from . import template  # noqa: F401,E402
from . import tools  # noqa: E402
from . import tun  # noqa: E402

app.add_typer(add.app)
app.add_typer(new.app)
app.add_typer(profile.app)
app.add_typer(secrets.app)
app.add_typer(tools.app)
app.add_typer(tun.app)


def main() -> None:
    additional_args = []
    for env in ("NYL_ARGS", "ARGOCD_ENV_NYL_ARGS"):
        if env in os.environ:
            additional_args = shlex.split(args_string := os.environ[env])
            logger.opt(colors=True).debug(
                "Adding additional arguments from <cyan>{}</>: <yellow>{}</>", env, args_string
            )
    sys.argv += additional_args
    logger.opt(colors=True).debug("Full Nyl command-line: <yellow>{}</>", shlex.join(sys.argv))
    app()
