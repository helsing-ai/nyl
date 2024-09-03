from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
from tempfile import TemporaryDirectory
import time
from typing import Any, TypedDict

import yaml
from loguru import logger

from nyl.tools.types import Manifests


@dataclass
class KubectlError(Exception):
    statuscode: int
    stderr: str | None = None

    def __str__(self) -> str:
        message = f"Kubectl command failed with status code {self.statuscode}"
        if self.stderr:
            message += f": {self.stderr}"
        return message


class KubectlVersion(TypedDict):
    major: str
    minor: str
    gitVersion: str
    gitCommit: str
    gitTreeState: str
    buildDate: str
    goVersion: str
    compiler: str
    platform: str


class Kubectl:
    """
    Wrapper for interfacing with `kubectl`.
    """

    def __init__(self) -> None:
        self.env: dict[str, str] = {}
        self.tempdir: TemporaryDirectory[str] | None = None

    def __del__(self) -> None:
        if hasattr(self, "tempdir") and self.tempdir is not None:
            logger.warning("Kubectl object was not cleaned up properly")
            self.tempdir.cleanup()

    def __enter__(self) -> "Kubectl":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.tempdir is not None:
            self.tempdir.cleanup()
            self.tempdir = None

    def set_kubeconfig(self, kubeconfig: dict[str, Any] | str | Path) -> None:
        """
        Set the kubeconfig to use for `kubectl` commands.
        """

        if self.tempdir is None:
            self.tempdir = TemporaryDirectory()

        if isinstance(kubeconfig, Path):
            kubeconfig_path = kubeconfig
        else:
            kubeconfig_path = Path(self.tempdir.name) / "kubeconfig"
            with open(kubeconfig_path, "w") as f:
                if isinstance(kubeconfig, str):
                    f.write(kubeconfig)
                else:
                    yaml.safe_dump(kubeconfig, f)

        self.env["KUBECONFIG"] = str(kubeconfig_path)

    def apply(
        self,
        manifests: Manifests,
        force_conflicts: bool = False,
        server_side: bool = True,
        applyset: str | None = None,
        prune: bool = False,
    ) -> None:
        """
        Apply the given manifests to the cluster.
        """

        env = self.env
        command = ["kubectl", "apply", "-f", "-"]
        if server_side:
            command.append("--server-side")
        if applyset:
            env = env.copy()
            env["KUBECTL_APPLYSET"] = "true"
            command.extend(["--applyset", applyset])
        if prune:
            command.append("--prune")
        if force_conflicts:
            command.append("--force-conflicts")

        logger.debug("Applying manifests with command: $ {command}", command=" ".join(map(shlex.quote, command)))
        status = subprocess.run(command, input=yaml.safe_dump_all(manifests), text=True, env={**os.environ, **env})
        if status.returncode:
            raise KubectlError(status.returncode)

    def cluster_info(self, retries: int = 0, retry_interval_seconds: int = 10) -> str:
        """
        Get the cluster info.
        """

        status: subprocess.CompletedProcess[str]
        for _ in range(retries + 1):
            status = subprocess.run(
                ["kubectl", "cluster-info"],
                env={**os.environ, **self.env},
                text=True,
                capture_output=True,
            )
            if status.returncode == 0:
                return status.stdout

            time.sleep(retry_interval_seconds)

        raise KubectlError(status.returncode, status.stderr)

    def version(self) -> KubectlVersion:
        output = subprocess.check_output(["kubectl", "version", "-o", "json", "--client=true"], text=True)
        return json.loads(output)["clientVersion"]  # type: ignore[no-any-return]
