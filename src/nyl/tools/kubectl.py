import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, TypedDict

import yaml
from loguru import logger

from nyl.resources.applyset import APPLYSET_LABEL_PART_OF, ApplySet
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd
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

        logger.debug("Applying manifests with command: $ {command}", command=lazy_str(pretty_cmd, command))
        status = subprocess.run(command, input=yaml.safe_dump_all(manifests), text=True, env={**os.environ, **env})
        if status.returncode:
            raise KubectlError(status.returncode)

    def diff(
        self,
        manifests: Manifests,
        applyset: ApplySet | None = None,
        on_error: Literal["raise", "return"] = "raise",
    ) -> Literal["no-diff", "diff", "error"]:
        """
        Diff the given manifests against the cluster.

        Args:
            manifests: The input manifests.
            on_error: What to do if the diff command fails. If "raise", raise a KubectlError. If "return", return the
                status code.
            applyset: The applyset to use for the diff. This can only be combined with the `prune` option.
            prune: Include resources that would be deleted by pruning.
        """

        match_labels = {}

        # As of kubectl 1.31, the --prune flag is not supported with --applyset. This is a workaround to allow the
        # user to specify the applyset reference and the prune option at the same time.
        if applyset:
            match_labels[APPLYSET_LABEL_PART_OF] = applyset.id

        command = ["kubectl", "diff", "-f", "-"]
        if match_labels:
            command.extend(["-l", ",".join(f"{k}={v}" for k, v in match_labels.items())])

        logger.debug("Diffing manifests with command: $ {command}", command=lazy_str(pretty_cmd, command))
        status = subprocess.run(command, input=yaml.safe_dump_all(manifests), text=True)
        if status.returncode == 1:
            return "diff"
        elif status.returncode == 0:
            return "no-diff"
        elif on_error == "return":
            return "error"
        else:
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
