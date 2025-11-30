"""Template context model for Nyl template command.

This model encapsulates the shared state and configuration needed
during template command execution.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nyl.core.di import DIContainer
from nyl.project.config import ProjectConfig


@dataclass
class TemplateContext:
    """Context for template command execution.

    Includes configuration specific to template rendering
    and resource application.
    """

    container: DIContainer
    """Dependency injection container for this execution"""

    project_config: ProjectConfig
    """Project configuration loaded from nyl-project.yaml"""

    working_dir: Path
    """Current working directory for the command"""

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

    mode: Literal["apply", "diff"] | None = None
    """Execution mode: 'apply' to apply resources, 'diff' to show differences, None for dry-run"""

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
