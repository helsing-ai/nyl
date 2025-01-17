from itertools import chain
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from loguru import logger

from nyl.resources import API_VERSION_INLINE, NylResource, ObjectMetadata
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd
from nyl.tools.types import Manifests

KyvernoPolicyDocument = dict[str, Any]
KyvernoPolicyRulesDocument = dict[str, Any]


@dataclass(kw_only=True)
class KyvernoSpec:
    policyFiles: list[str] = field(default_factory=list)
    """
    A list of Kyverno policy filenames, either relative to the file that defined the #PostProcessor resource
    or discoverable in the project search path.
    """

    inlinePolicies: dict[str, KyvernoPolicyDocument] = field(default_factory=dict)
    """
    A mapping of policy name to the Kyverno policy document. Allows specifying Kyverno policies to be applied
    to the generated manifests inline.
    """


@dataclass(kw_only=True)
class PostProcessorSpec:
    kyverno: KyvernoSpec | None = None
    """
    Configure Kyverno policies to apply.
    """

    kyvernoRules: list[KyvernoPolicyRulesDocument] = field(default_factory=list)
    """
    Define rules for a single Kyverno `ClusterPolicy` to apply. The `name` field of the rule configuration may be
    ommited. Applies after policies defined in `kyverno`.

    To find more about Kyverno policies and rules, read https://kyverno.io/docs/writing-policies/.
    """

    def __post_init__(self) -> None:
        if self.kyvernoRules and self.kyverno:
            raise ValueError("Only one of `kyvernoRules` or `kyverno` may be specified.")

    def get_policy_files(self, name: str, workdir: Path, tmpdir: Path) -> list[Path]:
        """
        Get the paths to the Kyverno policy files to apply.

        Args:
            name: The name of the `ClusterPolicy` generated if `kyvernoRules` is specified.
            workdir: Policies referenced by a relative path will be resolved relative to this directory.
            tmpdir: Policies that are defined inline will be written to files in this directory.
        """

        files = []

        for policy in map(Path, self.kyverno.policyFiles if self.kyverno else ()):
            if (workdir / policy).exists():
                policy = (workdir / policy).resolve()
            assert policy.is_file() or policy.is_dir(), f"Path '{policy}' must be a directory or file"
            files.append(policy)

        for key, value in self.kyverno.inlinePolicies.items() if self.kyverno else ():
            # If the file name does not end with a YAML suffix, Kyverno will ignore the input file.
            if not key.endswith(".yml") and not key.endswith(".yaml"):
                key += ".yaml"
            files.append(tmpdir.joinpath(key))
            files[-1].write_text(yaml.safe_dump(value))

        if self.kyvernoRules:
            # Ensure each rule has a name field.
            rules = [{"name": f"{name}-{idx}", **rule} for idx, rule in enumerate(self.kyvernoRules)]
            cluster_policy = {
                "apiVersion": "kyverno.io/v1",
                "kind": "ClusterPolicy",
                "metadata": {"name": name},
                "spec": {"rules": rules},
            }
            files.append(tmpdir.joinpath(f"generated-{name}.yaml"))
            files[-1].write_text(yaml.safe_dump(cluster_policy))

        return files


@dataclass(kw_only=True)
class PostProcessor(NylResource, api_version=API_VERSION_INLINE):
    """
    Configuration for post-processing Kubernetes manifests in a file. Note that the post-processing is always
    scoped to the file that the processor is defined in. Post processors will be applied after all inline resources
    are reconciled.

    Important: Kyverno injects `namespace: default` into resources that don't have it. Because Nyl implements its
    own way of backfilling the `namespace` metadata field, the PostProcessor should be run _after_ that fallback
    is applied.
    """

    # Specifying metadata for a PostProcessor resource is optional, since it does not need to be identifiable.
    # Giving it a name will have that name be populated into the generated Kyverno ClusterPolicy when using
    # the :attr:`PostProcessorSpec.kyvernoRules` field.
    metadata: ObjectMetadata | None = None

    spec: PostProcessorSpec

    def process(self, manifests: Manifests, source_file: Path) -> Manifests:
        """
        Post-process the given manifests.
        """

        with TemporaryDirectory() as _tmp:
            policy_files = self.spec.get_policy_files(
                name=self.metadata.name if self.metadata else "unnamed",
                workdir=source_file.parent,
                tmpdir=Path(_tmp),
            )

            if policy_files:
                logger.info(
                    "Applying {} Kyverno {} to manifests from '{}': {}",
                    len(policy_files),
                    "policy" if len(policy_files) == 1 else "policies",
                    source_file.name,
                    ", ".join(f"{policy_file.name}" for policy_file in policy_files),
                )

                manifests = apply_kyverno_policies(
                    resources=manifests,
                    policy_files=policy_files,
                )

        return manifests

    @staticmethod
    def extract_from_list(manifests: Manifests) -> tuple[Manifests, list["PostProcessor"]]:
        processors = []
        new_manifests = Manifests([])
        for manifest in list(manifests):
            if processor := PostProcessor.maybe_load(manifest):
                processors.append(processor)
            else:
                new_manifests.append(manifest)
        return new_manifests, processors

    @staticmethod
    def apply_all(manifests: Manifests, processors: list["PostProcessor"], source_file: Path) -> Manifests:
        for processor in processors:
            manifests = processor.process(manifests, source_file)
        return manifests


def apply_kyverno_policies(
    resources: Manifests,
    policy_files: list[Path],
    kyverno_bin: Path | str = "kyverno",
) -> Manifests:
    with TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)

        # Write all resources to a single manifest file as input to Kyverno.
        manifest_file = tmp / "manifest.yaml"
        manifest_file.write_text(yaml.safe_dump_all(resources))

        # Create an output directory for Kyverno to write the mutated manifests to.
        output_dir = tmp / "output"
        output_dir.mkdir()

        command = [
            str(kyverno_bin),
            "apply",
            *map(str, policy_files),
            f"--resource={manifest_file}",
            "-o",
            str(output_dir),
        ]

        logger.debug("$ {}", lazy_str(pretty_cmd, command))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

        if result.returncode != 0:
            logger.error("Kyverno stdout:\n{}", result.stdout.decode())
            raise RuntimeError("Kyverno failed to apply policies to manifests. See logs for more details")
        else:
            logger.debug("Kyverno stdout:\n{}", result.stdout.decode())

        # Load all resources (Kyverno generates one file per resource, including unchanged ones).
        new_resources = Manifests(
            list(chain(*(filter(None, yaml.safe_load_all(file.read_text())) for file in output_dir.iterdir())))
        )
        if len(new_resources) != len(resources):
            # Showing identifies for manifests that have been added or removed is not very helpful because
            # Kyverno will add `namespace: default` to those without the field, which changes the identifier.
            raise RuntimeError(
                "Unexpected behaviour of `kyverno apply` command: The number of resources generated in the "
                f"output folder ({len(new_resources)}) does not match the number of input resources "
                f"({len(resources)})."
            )

    return new_resources
