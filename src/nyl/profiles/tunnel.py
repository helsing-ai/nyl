import os
import random
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from loguru import logger
from stablehash import stablehash

from nyl.tools.kvstore import JsonFileKvStore, SerializingStore
from nyl.tools.shell import pretty_cmd


@dataclass
class TunnelSpec:
    """
    Defines an SSH tunel that is to be opened.
    """

    @dataclass
    class Forwarding:
        host: str
        port: int

    @dataclass(frozen=True)
    class Locator:
        config_file: str
        profile: str

        def __str__(self) -> str:
            return f"{self.config_file}:{self.profile}"

    locator: Locator
    " Locator for where the tunnel spec is defined."

    forwardings: dict[str, Forwarding]
    """ A map from forwarding alias to forwarding configuration. The local ports will be randomly assigned.
    and must be obtained from the [TunnelStatus]. """

    user: str
    host: str
    identity_file: str | None = None


@dataclass
class TunnelStatus:
    """
    Represents the current status of a tunnel.
    """

    id: str
    """ A unique ID for the tunel. """

    status: Literal["open", "broken", "closed"]
    """ The status of the tunnel, broken if the SSH process is down. """

    ssh_pid: int | None
    """ The process ID of the SSH tunnel. """

    local_ports: dict[str, int]
    """ A map from forwarding alias to local port. """

    spec_hash: str
    """ Last known hash of the tunnel spec. Used to determine if the tunnel needs to be restarted. """

    @staticmethod
    def empty() -> "TunnelStatus":
        return TunnelStatus("", "closed", None, {}, "")


class TunnelManager:
    """
    Helper class to manage SSH tunnels.

    Before the tunnel manager can be used, its context manager must be entered to lock the global state.
    """

    DEFAULT_STATE_DIR = Path.home() / ".nyl" / "tunnels"

    def __init__(self, state_dir: Path | None = None) -> None:
        """
        Args:
            state_dir: Path to the directory where the tunnel manager stores its global state.
        """

        state_dir = state_dir or self.DEFAULT_STATE_DIR
        self._store = SerializingStore[tuple[TunnelSpec, TunnelStatus]](
            tuple[TunnelSpec, TunnelStatus],
            JsonFileKvStore(file=state_dir / "state.json", lockfile=state_dir / ".lock"),
        )

    def __enter__(self) -> "TunnelManager":
        self._store.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        self._store.__exit__(*args)

    def _refresh_status(self, status: TunnelStatus) -> None:
        # Check if the SSH process is still running.
        if status.ssh_pid is not None:
            try:
                os.kill(status.ssh_pid, 0)
            except ProcessLookupError:
                status.status = "broken"
                status.ssh_pid = None
            else:
                status.status = "open"

    def _close_tunnel(self, status: TunnelStatus) -> None:
        if status.ssh_pid is not None:
            try:
                os.kill(status.ssh_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            # Wait for the process to terminate.
            try:
                os.waitpid(status.ssh_pid, 0)
            except ChildProcessError:
                pass

        status.status = "closed"
        status.ssh_pid = None
        status.local_ports = {}

    def get_tunnels(self) -> Iterable[tuple[TunnelSpec, TunnelStatus]]:
        """
        Get the status of all tunnels, refreshing the status of each tunnel.
        """

        for key in self._store.list():
            spec, status = self._store.get(key)
            self._refresh_status(status)
            self._store.set(key, (spec, status))
            yield spec, status

    def get_tunnel(self, locator: TunnelSpec.Locator) -> tuple[TunnelSpec, TunnelStatus] | None:
        """
        Retrieve the last known tunnel status and spec based on the tunnel locator.
        """

        try:
            spec, status = self._store.get(str(locator))
        except KeyError:
            return None

        self._refresh_status(status)
        self._store.set(str(locator), (spec, status))
        return spec, status

    def open_tunnel(self, spec: TunnelSpec) -> TunnelStatus:
        """
        Open a tunnel per the given spec. If a tunnel for the same spec already exists, is is ensures that the tunnel
        state is up-to-date, which may result in restarting the tunnel. If the tunnel is broken, it is restarted.

        Args:
            spec: The tunnel specification.
        Returns:
            The status of the tunnel.
        """

        # Find the tunnel status for the given spec by the spec's locator string.
        try:
            status = self._store.get(str(spec.locator))[1]
        except KeyError:
            status = None

        # Check if the tunnel is open and up-to-date.
        spec_hash = stablehash(spec).hexdigest()
        if status is not None and status.status == "open" and status.spec_hash == spec_hash:
            logger.opt(colors=True).info("Reusing existing SSH tunnel.", spec.locator)
            return status

        # Close the tunnel if it is open.
        if status is not None:
            self._close_tunnel(status)
            status = None

        # Open a new tunnel.
        status = TunnelStatus(
            id=new_tunnel_id(),
            status="closed",
            ssh_pid=None,
            local_ports={},
            spec_hash=spec_hash,
        )

        # Preliminary status update.
        self._store.set(str(spec.locator), (spec, status))

        # Allocate local ports. (TODO: This should be done in a more robust way.)
        status.local_ports = {alias: random.randint(10000, 20000) for alias in spec.forwardings}

        # Start the SSH tunnel.
        ssh_args = [
            "ssh",
            "-N",
            "-L",
            ",".join(
                f"{status.local_ports[alias]}:{forwarding.host}:{forwarding.port}"
                for alias, forwarding in spec.forwardings.items()
            ),
            f"{spec.user}@{spec.host}",
        ]
        if spec.identity_file is not None:
            ssh_args.extend(["-i", spec.identity_file])

        logger.opt(colors=True).info("Opening SSH tunnel with <yellow>$ {}</>.", pretty_cmd(ssh_args))
        proc = subprocess.Popen(ssh_args)

        # Update the status.
        status.status = "open"
        status.ssh_pid = proc.pid

        self._store.set(str(spec.locator), (spec, status))

        return status

    def close_tunnel(self, locator: TunnelSpec.Locator) -> TunnelStatus:
        """
        Close a tunnel by it's locator.
        """

        try:
            spec, status = self._store.get(str(locator))
        except KeyError:
            logger.warning("No tunnel found for '{}'.", locator)
            return TunnelStatus("", "closed", None, {}, "")

        self._refresh_status(status)
        if status.status == "open":
            logger.debug("Closing tunnel for '{}'.", locator)
        else:
            logger.debug("Tunnel for '{}' is already closed.", locator)
        # Always call close_tunnel to ensure the tunnel to ensure the state is transitioned to "closed".
        self._close_tunnel(status)
        self._store.set(str(locator), (spec, status))
        return status


def new_tunnel_id() -> str:
    """
    Generate a new unique tunnel ID.
    """

    return f"tun{random.randint(1000, 9999)}"
