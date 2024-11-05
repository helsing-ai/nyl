"""
Access SSH tunnels globally managed by Nyl.
"""

from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table
from typer import Argument, Typer

from nyl.commands import PROVIDER
from nyl.profiles import get_tunnel_spec
from nyl.profiles.config import ProfileConfig
from nyl.profiles.tunnel import TunnelManager, TunnelSpec, TunnelStatus
from nyl.tools.fs import shorter_path
from nyl.tools.typer import new_typer

app: Typer = new_typer(name="tun", help=__doc__)


@app.command()
def status(all: bool = False) -> None:
    """
    Show the status of all tunnels.
    """

    config = PROVIDER.get(ProfileConfig)

    table = Table()
    table.add_column("Source", style="blue")
    table.add_column("Profile", justify="right", style="cyan")
    table.add_column("Tunnel ID")
    table.add_column("Status")
    table.add_column("Proxy")
    table.add_column("Forwardings")

    print(f"Showing tunnels from '{config.file}'" + (" an all other known tunnels." if all else "."))

    with TunnelManager() as manager:
        tunnels = list(manager.get_tunnels())

        # Group tunnels by profile which are in the current profile configuration file.
        tunnel_by_profile = {
            spec.locator.profile: (spec, status)
            for spec, status in tunnels
            if spec.locator.config_file == str(config.file)
        }

        # Backfill any tunnels that we could open from the current profile, but haven't yet. We can only
        # add profiles which are defined in the current known profile configuration file and not any others
        # on the system, while there may be tunnel information available for them from previous runs.
        for profile_name, profile in config.profiles.items():
            if profile_name not in tunnel_by_profile and profile.tunnel:
                assert config.file is not None, "Profile configuration file must be set."
                tunnels.append((get_tunnel_spec(config.file, profile_name, profile.tunnel), TunnelStatus.empty()))

        tunnels.sort(key=lambda x: (x[0].locator.profile, x[0].locator.config_file))

        for spec, status in tunnels:
            # Unless we want to show all tunnels, only show the ones from the current profile configuration file.
            if not all and spec.locator.config_file != str(config.file):
                continue

            profile_name = spec.locator.profile

            forwardings = ", ".join(
                f"localhost:{status.local_ports.get(k, '?')} → {v.host}:{v.port}" for k, v in spec.forwardings.items()
            )
            table.add_row(
                str(shorter_path(Path(spec.locator.config_file))),
                profile_name,
                status.id,
                status.status,
                f"{spec.user}@{spec.host}",
                forwardings,
            )

    Console().print(table)


@app.command()
def start(profile_name: str = Argument("default", envvar="NYL_PROFILE")) -> None:
    """
    Open a tunnel to the cluster targeted by the profile.
    """

    config = PROVIDER.get(ProfileConfig)

    try:
        profile = config.profiles[profile_name]
    except KeyError:
        logger.error("Profile '{}' not found in '{}'.", profile_name, config.file)
        exit(1)

    if not profile.tunnel:
        raise ValueError(f"Profile '{profile_name}' does not have a tunnel configuration.")

    # TODO: Know the Kubernetes host/port to forward.
    spec = TunnelSpec(
        locator=TunnelSpec.Locator(str(config.file), profile_name),
        forwardings={"kubernetes": TunnelSpec.Forwarding(host="localhost", port=6443)},
        user=profile.tunnel.user,
        host=profile.tunnel.host,
        identity_file=profile.tunnel.identity_file,
    )

    with TunnelManager() as manager:
        manager.open_tunnel(spec)


@app.command()
def stop(profile_name: str = Argument("default", envvar="NYL_PROFILE"), all: bool = False) -> None:
    """
    Close all tunnels or the tunnel for a specific profile.
    """

    if all:
        with TunnelManager() as manager:
            for spec, _status in manager.get_tunnels():
                manager.close_tunnel(spec.locator)
        return

    config = PROVIDER.get(ProfileConfig)
    with TunnelManager() as manager:
        manager.close_tunnel(TunnelSpec.Locator(str(config.file), profile_name))
