"""Specific error types for Nyl operations.

These error classes provide structured, actionable error messages
for common failure scenarios in Nyl commands.
"""

from typing import Any

from nyl.core.errors import NylError


class ManifestValidationError(NylError):
    """Raised when a manifest file has invalid structure or content."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        hint: str | None = None,
        cause: Exception | None = None,
    ):
        """Create a manifest validation error.

        Args:
            message: Description of what's wrong with the manifest
            file_path: Path to the problematic manifest file
            hint: Suggestion for how to fix the issue
            cause: Underlying exception if any
        """
        details: dict[str, Any] = {}
        if file_path:
            details["file"] = file_path

        super().__init__(
            message=message,
            hint=hint,
            cause=cause,
            details=details,
        )


class ProfileNotFoundError(NylError):
    """Raised when a requested profile cannot be found."""

    def __init__(
        self,
        profile_name: str,
        available_profiles: list[str] | None = None,
        hint: str | None = None,
    ):
        """Create a profile not found error.

        Args:
            profile_name: Name of the profile that wasn't found
            available_profiles: List of available profile names
            hint: Custom hint, or auto-generated if not provided
        """
        details: dict[str, Any] = {"requested_profile": profile_name}

        if available_profiles:
            details["available_profiles"] = ", ".join(available_profiles)

        if hint is None and available_profiles:
            hint = f"Available profiles: {', '.join(available_profiles)}"
        elif hint is None:
            hint = "Check your nyl-profiles.yaml or nyl-project.yaml configuration"

        super().__init__(
            message=f"Profile '{profile_name}' not found",
            hint=hint,
            details=details,
        )


class NamespaceAmbiguityError(NylError):
    """Raised when namespace resolution is ambiguous."""

    def __init__(
        self,
        message: str,
        namespaces: list[str] | None = None,
        file_path: str | None = None,
        hint: str | None = None,
    ):
        """Create a namespace ambiguity error.

        Args:
            message: Description of the ambiguity
            namespaces: List of conflicting namespaces
            file_path: Path to the manifest file
            hint: Custom hint, or auto-generated if not provided
        """
        details: dict[str, Any] = {}
        if namespaces:
            details["namespaces_found"] = ", ".join(namespaces)
        if file_path:
            details["file"] = file_path

        if hint is None and namespaces:
            hint = (
                "Use --namespace to specify the default namespace, or add the "
                "'nyl.io/is-default-namespace: \"true\"' annotation to one of the Namespace resources"
            )
        elif hint is None:
            hint = "Specify --namespace or add a Namespace resource to your manifest"

        super().__init__(
            message=message,
            hint=hint,
            details=details,
        )


class ApplySetError(NylError):
    """Raised for ApplySet-related errors."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        applyset_count: int | None = None,
        hint: str | None = None,
        cause: Exception | None = None,
    ):
        """Create an ApplySet error.

        Args:
            message: Description of the ApplySet issue
            file_path: Path to the manifest file
            applyset_count: Number of ApplySets found (if relevant)
            hint: Suggestion for how to fix the issue
            cause: Underlying exception if any
        """
        details: dict[str, Any] = {}
        if file_path:
            details["file"] = file_path
        if applyset_count is not None:
            details["applysets_found"] = applyset_count

        if hint is None and applyset_count and applyset_count > 1:
            hint = "Only one ApplySet resource per manifest file is allowed. Remove duplicates or split into separate files."

        super().__init__(
            message=message,
            hint=hint,
            cause=cause,
            details=details,
        )


class KubernetesOperationError(NylError):
    """Raised when a Kubernetes operation fails."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        resource: str | None = None,
        hint: str | None = None,
        cause: Exception | None = None,
    ):
        """Create a Kubernetes operation error.

        Args:
            message: Description of what went wrong
            operation: The operation that failed (apply, diff, delete, etc.)
            resource: Resource identifier (kind/name or similar)
            hint: Suggestion for how to resolve the issue
            cause: Underlying exception if any
        """
        details: dict[str, Any] = {}
        if operation:
            details["operation"] = operation
        if resource:
            details["resource"] = resource

        super().__init__(
            message=message,
            hint=hint,
            cause=cause,
            details=details,
        )


class ConfigurationError(NylError):
    """Raised when there's an issue with Nyl configuration."""

    def __init__(
        self,
        message: str,
        config_file: str | None = None,
        setting: str | None = None,
        hint: str | None = None,
        cause: Exception | None = None,
    ):
        """Create a configuration error.

        Args:
            message: Description of the configuration issue
            config_file: Path to the problematic config file
            setting: Name of the problematic setting
            hint: Suggestion for how to fix the configuration
            cause: Underlying exception if any
        """
        details: dict[str, Any] = {}
        if config_file:
            details["config_file"] = config_file
        if setting:
            details["setting"] = setting

        super().__init__(
            message=message,
            hint=hint,
            cause=cause,
            details=details,
        )
