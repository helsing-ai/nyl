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
    """

    # metadata: ObjectMetadata

    spec: PostProcessorSpec

    def process(self, manifests: Manifests, source_file: Path) -> Manifests:
        """
        Post-process the given manifests.
        """

        if self.spec.kyverno.policyFiles or self.spec.kyverno.inlinePolicies:
            logger.info("Applying Kyverno policies to manifests from '{}': {}", source_file.name, self.spec.kyverno)

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

                # Write manifests to a file.
                manifests_file = tmp / "manifests.yaml"
                manifests_file.write_text(yaml.safe_dump_all(manifests))
                output_file = tmp / "output.yaml"

                command = [
                    "kyverno",
                    "apply",
                    *map(str, policy_paths),
                    f"--resource={manifests_file}",
                    "-o",
                    str(output_file),
                ]
                logger.debug("$ {}", lazy_str(pretty_cmd, command))
                subprocess.check_call(command, stdout=sys.stderr)  # TODO: Catch output?

                # Kyverno only prints the mutated manifests. We assume their name/kind doesn't change and
                # merge them back into the original list.
                mutated_manifests = Manifests(list(filter(None, yaml.safe_load_all(output_file.read_text()))))

                logger.info("  Mutated manifests: {}", ", ".join(map(resource_locator, mutated_manifests)))
                keyed_manifests = {resource_locator(m): m for m in manifests}
                keyed_manifests.update({resource_locator(m): m for m in mutated_manifests})
                manifests = Manifests(list(keyed_manifests.values()))

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
