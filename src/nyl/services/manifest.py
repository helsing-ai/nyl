"""Service for loading and processing Kubernetes manifest files."""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from nyl.models.errors import ManifestValidationError
from nyl.tools import yaml
from nyl.tools.types import Resource, ResourceList


@dataclass
class ManifestsWithSource:
    """Represents a list of resources loaded from a particular source file."""

    resources: ResourceList
    file: Path


class ManifestLoaderService:
    """Service for loading Kubernetes manifests from files and directories.

    This service handles:
    - Finding manifest files (with filtering for nyl- prefixes, hidden files, etc.)
    - Loading YAML content from files
    - Extracting local variables ($-prefixed keys) from manifests
    - Validating manifest structure
    """

    def load_manifests(self, paths: list[Path]) -> list[ManifestsWithSource]:
        """Load all resources from the given paths.

        Args:
            paths: List of file or directory paths to load manifests from

        Returns:
            List of ManifestsWithSource, one per file

        Note:
            - Directories are scanned non-recursively
            - Files starting with 'nyl-', '.', or '_' are skipped
            - Only files with .yaml extension are loaded
        """
        logger.trace("Loading manifests from paths: {}", paths)

        files = self._discover_files(paths)

        logger.trace("Files to load: {}", files)
        if len(files) == 0:
            logger.warning(
                "No valid manifests found in the paths. Nyl does not recursively enumerate directory contents, "
                "make sure you are specifying at least one path with valid YAML manifests to render."
            )

        result = []
        for file in files:
            try:
                resources = ResourceList(
                    list(map(Resource, filter(None, yaml.loads_all(file.read_text()))))
                )
                result.append(ManifestsWithSource(resources, file))
            except Exception as e:
                raise ManifestValidationError(
                    f"Failed to load manifest from {file}",
                    file_path=str(file),
                    hint="Check that the file contains valid YAML",
                    cause=e,
                )

        return result

    def extract_local_variables(
        self, source: ManifestsWithSource
    ) -> dict[str, any]:
        """Extract local variables from a manifest.

        Local variables are objects without apiVersion/kind that have keys
        starting with '$'. These are removed from the source and returned
        as a dictionary.

        Args:
            source: The manifest source to extract variables from (modified in-place)

        Returns:
            Dictionary of local variables (without the '$' prefix)

        Raises:
            ManifestValidationError: If a local variable object has invalid structure
        """
        local_vars = {}

        for resource in source.resources[:]:  # Iterate over copy
            # Skip Kubernetes resources
            if "apiVersion" in resource or "kind" in resource:
                continue

            # Check if this looks like a local variables object
            if not any(k.startswith("$") for k in resource.keys()):
                # Neither a Kubernetes object, nor one defining local variables
                continue

            # Validate that ALL keys start with '$'
            invalid_keys = [k for k in resource.keys() if not k.startswith("$")]
            if invalid_keys:
                raise ManifestValidationError(
                    f"Object defining local variables in {source.file} has keys that don't start with '$'",
                    file_path=str(source.file),
                    hint="All keys in a local variable definition must start with '$'. "
                    f"Invalid keys: {', '.join(invalid_keys)}",
                )

            # Extract variables (remove '$' prefix)
            for key, value in resource.items():
                local_vars[key[1:]] = value

            # Remove this resource from the list
            source.resources.remove(resource)

        return local_vars

    def validate_manifest_structure(self, source: ManifestsWithSource) -> None:
        """Validate the structure of a loaded manifest.

        Args:
            source: The manifest to validate

        Raises:
            ManifestValidationError: If the manifest has structural issues
        """
        for resource in source.resources:
            # Skip local variable definitions (already validated in extract_local_variables)
            if "apiVersion" not in resource and "kind" not in resource:
                continue

            # Validate required fields for Kubernetes resources
            if "apiVersion" not in resource:
                raise ManifestValidationError(
                    f"Resource in {source.file} is missing 'apiVersion' field",
                    file_path=str(source.file),
                    hint="All Kubernetes resources must have an 'apiVersion' field",
                )

            if "kind" not in resource:
                raise ManifestValidationError(
                    f"Resource in {source.file} is missing 'kind' field",
                    file_path=str(source.file),
                    hint="All Kubernetes resources must have a 'kind' field",
                )

    def _discover_files(self, paths: list[Path]) -> list[Path]:
        """Discover manifest files from the given paths.

        Args:
            paths: List of file or directory paths

        Returns:
            List of files to load
        """
        files = []
        for path in paths:
            if path.is_dir():
                for item in path.iterdir():
                    if self._should_skip_file(item):
                        continue
                    files.append(item)
            else:
                files.append(path)

        return files

    def _should_skip_file(self, path: Path) -> bool:
        """Check if a file should be skipped during discovery.

        Args:
            path: File path to check

        Returns:
            True if the file should be skipped
        """
        return (
            path.name.startswith("nyl-")
            or path.name.startswith(".")
            or path.name.startswith("_")
            or path.suffix != ".yaml"
            or not path.is_file()
        )
