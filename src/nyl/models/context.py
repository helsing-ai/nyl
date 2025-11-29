"""Execution context models for Nyl commands.

These models encapsulate the shared state and configuration needed
during command execution, making it easier to pass context through
service layers without global state.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nyl.core.di import DIContainer
from nyl.project.config import ProjectConfig


@dataclass
class ExecutionContext:
    """Base execution context shared across all commands.

    This context contains the fundamental dependencies and configuration
    needed by any Nyl command execution.
    """

    container: DIContainer
    """Dependency injection container for this execution"""

    project_config: ProjectConfig
    """Project configuration loaded from nyl-project.yaml"""

    working_dir: Path
    """Current working directory for the command"""

    def __post_init__(self) -> None:
        """Validate the context after initialization."""
        if not self.working_dir.exists():
            raise ValueError(f"Working directory does not exist: {self.working_dir}")


@dataclass
class TemplateContext(ExecutionContext):
    """Extended context for template command execution.

    Includes additional configuration specific to template rendering
    and resource application.
    """

    profile_name: str | None = None
    """Name of the active profile, if any"""

    secrets_provider_name: str | None = None
    """Name of the secrets provider, if any"""

    state_dir: Path | None = None
    """Directory for storing Nyl state"""

    cache_dir: Path | None = None
    """Directory for caching resources"""

    inline: bool = True
    """Whether to inline generated resources"""

    jobs: int | None = None
    """Number of parallel jobs for processing"""

    default_namespace: str | None = None
    """Default namespace for resources"""

    apply_mode: bool = False
    """Whether to apply resources to cluster"""

    diff_mode: bool = False
    """Whether to show diff against cluster"""

    prune: bool = False
    """Whether to prune resources not in manifest"""

    def get_state_dir(self) -> Path:
        """Get the state directory, creating it if needed."""
        if self.state_dir is None:
            base = self.project_config.file.parent if self.project_config.file else self.working_dir
            self.state_dir = base / ".nyl"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        return self.state_dir

    def get_cache_dir(self) -> Path:
        """Get the cache directory, creating it if needed."""
        if self.cache_dir is None:
            self.cache_dir = self.get_state_dir() / "cache"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir
