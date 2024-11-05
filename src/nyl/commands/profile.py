"""
Interact with your Nyl profile configuration.
"""

import shlex

from typer import Argument, Typer

from nyl.commands import PROVIDER
from nyl.profiles import ProfileManager
from nyl.tools.typer import new_typer

app: Typer = new_typer(name="profile", help=__doc__)


@app.command()
def activate(profile_name: str = Argument("default", envvar="NYL_PROFILE")) -> None:
    """
    Activate a Nyl profile.

    Evaluate the stdout of this command to export the KUBECONFIG into your environment.
    """

    with PROVIDER.get(ProfileManager) as manager:
        profile = manager.activate_profile(profile_name)

    for key, value in profile.env.items():
        print(f"export {key}={shlex.quote(value)}")


@app.command()
def get_kubeconfig(profile_name: str = Argument("default", envvar="NYL_PROFILE")) -> None:
    """
    Similar to `nyl profile activate`, but prints only the path to the `KUBECONFIG` file.
    """

    with PROVIDER.get(ProfileManager) as manager:
        profile = manager.activate_profile(profile_name)

    print(profile.kubeconfig)
