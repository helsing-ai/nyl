from itertools import chain
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from loguru import logger

from nyl.resources import API_VERSION_INLINE, NylResource
from nyl.tools.kubernetes import resource_locator
from nyl.tools.logging import lazy_str
from nyl.tools.shell import pretty_cmd
from nyl.tools.types import Manifests

KyvernoPolicyDocument = dict[str, Any]


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
    kyverno: KyvernoSpec
    """
    Apply Kyverno policies.
    """


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

    # metadata: ObjectMetadata

    spec: PostProcessorSpec

    def process(self, manifests: Manifests, source_file: Path) -> Manifests:
        """
        Post-process the given manifests.
        """

        if self.spec.kyverno.policyFiles or self.spec.kyverno.inlinePolicies:
            policy_paths = []

            for policy in map(Path, self.spec.kyverno.policyFiles):
                if (source_file.parent / policy).exists():
                    policy = (source_file.parent / policy).resolve()

                assert policy.is_file() or policy.is_dir(), f"Path '{policy}' must be a directory or file"
                # TODO: Resolve relative paths to full paths.
                policy_paths.append(Path(policy))

            with TemporaryDirectory() as _tmp:
                tmp = Path(_tmp)

                # Write inline policies to files.
                inline_dir = tmp / "inline-policies"
                inline_dir.mkdir()
                for key, value in self.spec.kyverno.inlinePolicies.items():
                    # If the file name does not end with a YAML suffix, Kyverno will ignore the input file.
                    if not key.endswith(".yml") and not key.endswith(".yaml"):
                        key += ".yaml"
                    policy_paths.append(inline_dir.joinpath(key))
                    policy_paths[-1].write_text(yaml.safe_dump(value))

                logger.info(
                    "Applying {} Kyverno {} to manifests from '{}'.",
                    len(policy_paths),
                    "policy" if len(policy_paths) == 1 else "policies",
                    source_file.name,
                )

                # Write manifests to a file.
                manifests_file = tmp / "manifests.yaml"
                manifests_file.write_text(yaml.safe_dump_all(manifests))
                output_dir = tmp / "output"
                output_dir.mkdir()

                command = [
                    "kyverno",
                    "apply",
                    *map(str, policy_paths),
                    f"--resource={manifests_file}",
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
                mutated_manifests = Manifests(
                    list(chain(*(filter(None, yaml.safe_load_all(file.read_text())) for file in output_dir.iterdir())))
                )
                if len(mutated_manifests) != len(manifests):
                    # Showing identifies for manifests that have been added or removed is not very helpful because
                    # Kyverno will add `namespace: default` to those without the field, which changes the identifier.
                    raise RuntimeError(
                        "Unexpected behaviour of `kyverno apply` command: The number of manifests generated in the "
                        f"output folder ({len(mutated_manifests)}) does not match the number of input manifests "
                        f"({len(manifests)})."
                    )

                manifests = mutated_manifests

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
