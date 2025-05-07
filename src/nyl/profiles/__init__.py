import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import requests.adapters
import urllib3
from loguru import logger
from nr.stream import Optional

from .config import LocalKubeconfig, Profile, ProfileConfig, SshTunnel
from .kubeconfig import KubeconfigManager
from .tunnel import TunnelManager, TunnelSpec

DEFAULT_PROFILE = "default"


@dataclass
class ActivatedProfile:
    kubeconfig: Path

    @property
    def env(self) -> dict[str, str]:
        return {
            # For standard tooling, like kubectl.
            "KUBECONFIG": str(self.kubeconfig.absolute()),
            # Used by Terraform providers.
            "KUBE_CONFIG_PATH": str(self.kubeconfig.absolute()),
        }


@dataclass
class ProfileManager:
    """
    This class combines the [TunnelManager] and [KubeconfigManager] to provide a holistic interface for managing
    connections and configuration to Kubernetes clusters.
    """

    config: ProfileConfig
    tunnels: TunnelManager
    kubeconfig: KubeconfigManager

    def __post_init__(self) -> None:
        # We don't need to enter the TunnelsManager context manager until we actually need to open a tunnel.
        self._tunnels_entered: bool = False

    def __enter__(self) -> "ProfileManager":
        return self

    def __exit__(self, *args: Any) -> None:
        if self._tunnels_entered:
            self.tunnels.__exit__(*args)

    def activate_profile(self, profile_name: str, update_process_env: bool = True) -> ActivatedProfile:
        """
        Ensure that the Kubernetes config and tunnel (if any) for the profile are available.

        Args:
            profile_name: The name of the profile to activate.
            update_process_env: If `True`, update the `KUBECONFIG` environment variable of the current process to
                                point to the activated profile's Kubeconfig file.
        """

        logger.opt(colors=True).info("Activating profile <magenta>{}</>...", profile_name)

        # If the requested profile is the default profile and it is not explicitly defined in the configuration,
        # create an implicit default profile with empty values. This ensures that the system can operate with a
        # fallback profile even when no specific configuration is provided for the default profile.
        if profile_name == DEFAULT_PROFILE and profile_name not in self.config.profiles:
            profile = Profile(values={}, kubeconfig=LocalKubeconfig(), tunnel=None)
        else:
            profile = self.config.profiles[profile_name]

        raw_kubeconfig = self.kubeconfig.get_raw_kubeconfig(profile_name, profile.kubeconfig)

        if profile.tunnel:
            # If the tunnel manager has not been entered yet, do so now.
            if not self._tunnels_entered:
                self.tunnels.__enter__()
                self._tunnels_entered = True

            # forwardings = {"kubernetes": f"{raw_kubeconfig.api_host}:{raw_kubeconfig.api_port}"}
            assert self.config.file is not None, "Profile configuration file must be set."
            tun_spec = get_tunnel_spec(self.config.file, profile_name, profile.tunnel)
            tun_status = Optional(self.tunnels.get_tunnel(tun_spec.locator)).map(lambda x: x[1]).or_else(None)
            # is_restarted = tun_status is None or tun_status.status != "open"
            tun_status = self.tunnels.open_tunnel(tun_spec)
            # tun_description = f" → {profile.tunnel.user}@{profile.tunnel.host} → {forwardings['kubernetes']}"

            raw_kubeconfig.api_host = "localhost"
            raw_kubeconfig.api_port = tun_status.local_ports["kubernetes"]

            # If the tunnel was only just started, it may need some time to connect.
            # timeout = 30 if is_restarted else 2
        # else:
        #     tun_description = ""
        #     timeout = 2

        activated_profile = ActivatedProfile(
            kubeconfig=self.kubeconfig.get_updated_kubeconfig(
                profile_name=profile_name,
                path=raw_kubeconfig.path,
                context=raw_kubeconfig.context,
                api_host=raw_kubeconfig.api_host,
                api_port=raw_kubeconfig.api_port,
            )
        )

        # api_server = f"https://{raw_kubeconfig.api_host}:{raw_kubeconfig.api_port}"
        # logger.opt(colors=True).info("Waiting for API server connectivity (<blue>{}{}</>)", api_server, tun_description)
        # _wait_for_api_server(api_server, timeout)

        if update_process_env:
            logger.trace("Updating process environment with activated profile: {}", activated_profile.env)
            os.environ.update(activated_profile.env)

        return activated_profile

    @staticmethod
    def load(required: bool = True) -> "ProfileManager":
        """
        Load the profile manager from the default configuration file.

        Args:
            required: Passed on to [`ProfileConfig.load()`]. If it is set to `False`, the Nyl state directory
                is assumed relative to the current working directory (`./.nyl`).
        """

        config = ProfileConfig.load(required=required)
        context_dir = config.file.parent if config.file else Path.cwd()

        # TODO: Use NYL_STATE_DIR if set.
        tunnels = TunnelManager()
        kubeconfig = KubeconfigManager(
            cwd=context_dir,
            state_dir=context_dir / ".nyl" / "profiles",
        )
        return ProfileManager(config, tunnels, kubeconfig)


def _wait_for_api_server(url: str, timeout: float) -> None:
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(total=100, backoff_factor=0.2, backoff_max=2)
    )
    session = requests.Session()
    session.adapters["https://"] = adapter

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

        # Measure the time it takes for API server to respond. This is useful to clarify what took so long
        # for example for an SSH tunnel that has only just been created.
        tstart = time.time()
        response = session.get(url, timeout=timeout, verify=False)
        tdelta = time.time() - tstart
        logger.debug("{:.2f}s until successful API server connection.", tdelta)

    if response.json().get("kind") == "Status":
        # Looks well enough like a Kubernetes status object.
        return

    raise RuntimeError(f"Unexpected response from API server: {response.text}")


def get_tunnel_spec(config_file: Path, profile: str, conf: SshTunnel) -> TunnelSpec:
    return TunnelSpec(
        locator=TunnelSpec.Locator(str(config_file), profile),
        forwardings={"kubernetes": TunnelSpec.Forwarding(host="localhost", port=6443)},
        user=conf.user,
        host=conf.host,
        identity_file=conf.identity_file,
    )
