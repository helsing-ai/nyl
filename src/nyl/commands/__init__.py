"""
Nyl is a flexible configuration management tool for Kubernetes resources that can be used to generate and deploy
applications directly or integrate as an ArgoCD ConfigManagementPlugin.
"""

import atexit
import json
import os
from pathlib import Path
import time
from typing import Optional
from nyl import __version__
from enum import Enum
import sys
from loguru import logger
from typer import Option
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd
from nyl.tools.typer import new_typer


app = new_typer(help=__doc__)


from . import argocd  # noqa: E402
from . import crds  # noqa: F401,E402
from . import new  # noqa: E402
from . import profile  # noqa: E402
from . import run  # noqa: F401, E402
from . import secrets  # noqa: E402
from . import template  # noqa: F401,E402
from . import tools  # noqa: E402
from . import tun  # noqa: E402

app.add_typer(argocd.app)
app.add_typer(new.app)
app.add_typer(profile.app)
app.add_typer(secrets.app)
app.add_typer(tools.app)
app.add_typer(tun.app)


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
    start_time = time.perf_counter()

    if log_details:
        fmt = f"{LOG_TIME_FORMAT} | {LOG_LEVEL_FORAMT} | {LOG_DETAILS_FORMAT} | {LOG_MESSAGE_FORMAT}"
    else:
        fmt = f"{LOG_TIME_FORMAT} | {LOG_LEVEL_FORAMT} | {LOG_MESSAGE_FORMAT}"

    logger.remove()
    logger.add(sys.stderr, level=LogLevel.ERROR.name if quiet else log_level.name, format=fmt)
    if log_file:
        logger.add(log_file, level=log_level.name, format=fmt)
    logger.opt(ansi=True).debug("Nyl v{} run from <yellow>{}</>.", __version__, Path.cwd())

    # Log some helpful information for debugging purposes.
    logger.debug("Used command-line arguments: {}", lazy_str(pretty_cmd, sys.argv))
    logger.debug("Current working directory: {}", Path.cwd())
    log_env = {}
    for key, value in os.environ.items():
        if key.startswith("ARGOCD_") or key.startswith("NYL_") or key.startswith("KUBE_"):
            log_env[key] = value
    logger.debug("Nyl-relevant environment variables: {}", lazy_str(json.dumps, log_env, indent=2))

    atexit.register(
        # HACK: If we don't wrap it in a lambda, Loguru fails with "ValueError: call stack is not deep enough".
        # But we also need to wrap it so we capture the right end time.
        lambda *a: logger.debug(*a, time.perf_counter() - start_time),
        "Finished (nyl {}) in {:.2f}s",
        lazy_str(pretty_cmd, sys.argv),
    )


@app.command()
def version() -> None:
    """
    Print the version of Nyl.
    """

    print(f"Nyl v{__version__}")
    sys.exit(0)
