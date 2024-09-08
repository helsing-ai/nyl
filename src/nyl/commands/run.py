import atexit
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from loguru import logger
from typer import Argument, Option
import yaml
from nyl.profiles import ActivatedProfile, ProfileManager
from nyl.profiles.kubeconfig import _trim_to_context
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

    manager = ProfileManager.load(required=False)
    if manager and profile_name in manager.config.profiles:
        with manager:
            profile = manager.activate_profile(profile_name)
        kind = "profile"
        kubeconfig = profile.kubeconfig
    else:
        # Check if the context exists in the kubeconfig.
        kubeconfig = Path(os.environ.get("KUBECONFIG", "~/.kube/config")).expanduser()
        if not kubeconfig.is_file():
            logger.opt(ansi=True).info("Profile <yellow>{}</> not found.", profile_name)
            sys.exit(1)

        try:
            kubeconfig_data = yaml.safe_load(kubeconfig.read_text())
            kubeconfig_data = _trim_to_context(kubeconfig_data, profile_name)
        except ValueError:
            logger.debug("Failed to parse the kubeconfig file/find context '{}'.", profile_name)
            logger.opt(ansi=True).info("Profile <yellow>{}</> not found.", profile_name)
            sys.exit(1)
        else:
            if not inherit_kubeconfig:
                logger.opt(ansi=True).error(
                    "Found context <yellow>{}</> in the kubeconfig ({}), but no Nyl profile with that name. "
                    "Consider using --inherit-kubeconfig,-I to run the command in that Kubernetes context.",
                    profile_name,
                    kubeconfig,
                )
                sys.exit(1)

            logger.opt(ansi=True).info(
                "Falling back to context <yellow>{}</> from the kubeconfig ({}) due to --inherit-kubeconfig,-I option.",
                profile_name,
                kubeconfig,
            )
            kind = "context"

            # Write the kubeconfig to a temporary file.
            tmpdir = TemporaryDirectory()
            atexit.register(tmpdir.cleanup)
            kubeconfig = Path(tmpdir.name) / "kubeconfig"
            kubeconfig.write_text(yaml.dump(kubeconfig_data))
            kubeconfig.chmod(0o600)

    profile = ActivatedProfile(kubeconfig)
    logger.opt(ansi=True).info(
        "Running command `<blue>{}</>` with {} <yellow>{}</>.",
        lazy_str(pretty_cmd, command),
        kind,
        profile_name,
    )
    sys.exit(subprocess.run(command, env={**os.environ, **profile.env}).returncode)
