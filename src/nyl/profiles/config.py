from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loguru import logger

from nyl.tools.fs import find_config_file
from nyl.tools.loads import loadf


@dataclass
class Profile:
    """
    Represents a Kubernetes connection profile.
    """

    kubeconfig: LocalKubeconfig | KubeconfigFromSsh = field(default_factory=lambda: LocalKubeconfig())
    """
    Describe how the Kubeconfig is to be obtained.
    """

    tunnel: SshTunnel | None = None
    """
    Describe how to create an SSH tunnel to reach the Kubernetes cluster API.
    """


@dataclass(kw_only=True, frozen=True)
class LocalKubeconfig:
    """
    Use the local Kubeconfig file, either from the default location or a custom path specified in the environment.
    """

    type: Literal["local"] = "local"

    path: str | None = None
    """
    Path to the Kubernetes configuration file. Relative to the profile configuration file. If not specified, it falls
    back to the default location (per `KUBECONFIG` or otherwise `~/.kube/config`).
    """

    context: str | None = None
    """
    The context to use from the Kubeconfig file. If not specified, the current context is used.
    """


@dataclass(kw_only=True, frozen=True)
class KubeconfigFromSsh:
    """
    Represents how to obtain the Kubeconfig from an SSH connection.
    """

    type: Literal["ssh"] = "ssh"
    user: str
    """
    The username to connect to the remote host with.
    """

    host: str
    """
    The remote host to connect to.
    """

    identity_file: str | None = None
    """
    An SSH private key file to use for authentication.
    """

    path: str
    """
    The path where the Kubeconfig can be retrieved from.
    """

    context: str | None = None
    """
    The context to use from the Kubeconfig file. If not specified, the current context is used.
    """

    replace_apiserver_hostname: str | None = None
    """
    Replace the hostname in the apiserver configuration of the Kubeconfig. This is useful for example with K3s when
    reading reading the `/etc/rancher/k3s/k3s.yaml` file from a remote host, but the API server in that file is not
    reachable from the local machine (e.g. because it `0.0.0.0`).
    """


@dataclass(kw_only=True)
class SshTunnel:
    """
    Configuration for an SSH tunnel.
    """

    type: Literal["ssh"] = "ssh"

    user: str
    """
    The username to connect to the remote host with.
    """

    host: str
    """
    The host to tunnel through.
    """

    identity_file: str | None = None
    """
    An SSH private key file to use for authentication.
    """


@dataclass
class ProfileConfig:
    FILENAMES = ["nyl-profiles.yaml", "nyl-profiles.toml", "nyl-profiles.json"]
    GLOBAL_CONFIG_DIR = Path.home() / ".config" / "nyl"
    STATE_DIRNAME = ".nyl"

    file: Path | None
    profiles: dict[str, Profile]

    @staticmethod
    def load(file: Path | None = None, /, *, cwd: Path | None = None, required: bool = True) -> "ProfileConfig":
        """
        Load the profiles configuration from the given file or the default file. If the configuration file does not
        exist, an error is raised unless *required* is set to `False`, in which case an empty configuration is
        returned.
        """

        from databind.json import load as deser
        from nyl.project.config import ProjectConfig

        if file is None:
            file = find_config_file(ProfileConfig.FILENAMES, cwd, required=False)

            # Check if there is a project configuration and if it configures profiles.
            project = ProjectConfig.load_if_has_precedence(
                over=file,
                cwd=cwd,
                predicate=lambda cfg: bool(cfg.config.profiles),
            )
            if project:
                logger.debug("Using profiles from project configuration '{}'", project.file)
                return ProfileConfig(project.file, project.config.profiles)

            if file is None:
                file = find_config_file(ProfileConfig.FILENAMES, ProfileConfig.GLOBAL_CONFIG_DIR, required=False)

        if file is None:
            if required:
                raise FileNotFoundError(
                    f"Configuration file '{ProfileConfig.FILENAMES}' not found in '{Path.cwd()}', "
                    f"any of its parent directories or '{ProfileConfig.GLOBAL_CONFIG_DIR}'"
                )
            return ProfileConfig(None, {})

        logger.debug("Loading profiles configuration from '{}'", file)
        profiles = deser(loadf(file), dict[str, Profile], filename=str(file))
        return ProfileConfig(file, profiles)
