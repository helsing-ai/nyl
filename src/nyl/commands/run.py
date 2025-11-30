import os
import subprocess
import sys

from loguru import logger
from typer import Argument, Option

from nyl.core import DIContainer, setup_base_container
from nyl.profiles import ProfileManager
from nyl.services.profile import ProfileService
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd

from . import app

# app = new_typer(name="run", help=__doc__)


@app.command()
def run(
    profile_name: str = Option("default", "--profile", "-p", "-c", envvar="NYL_PROFILE"),
    inherit_kubeconfig: bool = Option(
        False,
        "--inherit-kubeconfig",
        "-I",
        help="If no `nyl-profiles.yaml` is found in the current directory, or if the specified profile is not found, "
        "look for a matching Kubernetes context in the global kube config and run the command in that context. This "
        "is useful to run `kubectl` commands without having to write logic to discriminate between cases where "
        "a cluster connection is configured via Nyl or not.",
    ),
    command: list[str] = Argument(..., help="The command to run under the `KUBECONFIG` of the given profile."),
) -> None:
    """
    Activate a Nyl profile and run a command in the context of the profile (i.e. with the same environment variables
    as printed by `nyl profile activate`).

    This is useful for running commands like `kubectl` without caring so much about whether the cluster connection is
    defined in a `nyl-profile.yaml` file or in the global kubeconfig. With the --inherit-kubeconfig option, you can
    simply name the cluster you want to use for the command and Nyl will either load the profile from the
    `nyl-profiles.yaml` configuration or from the same-named context in the global kubeconfig.
    """

    # Create DI container for this command execution
    container = DIContainer()
    setup_base_container(container)

    manager = container.resolve(ProfileManager)
    profile_service = ProfileService(manager)

    # Use ProfileService to resolve profile or kubeconfig context
    profile = profile_service.resolve_profile(
        profile_name,
        inherit_kubeconfig=inherit_kubeconfig,
        required=True,
    )
    assert profile is not None  # required=True ensures profile is returned

    # Determine if we're using a Nyl profile or kubeconfig context
    kind = "profile" if manager and profile_name in manager.config.profiles else "context"

    # Use ActivatedProfile as context manager to ensure cleanup
    with profile:
        logger.opt(colors=True).info(
            "Running command `<blue>{}</>` with {} <yellow>{}</>.",
            lazy_str(pretty_cmd, command),
            kind,
            profile_name,
        )
        sys.exit(subprocess.run(command, env={**os.environ, **profile.env}).returncode)
