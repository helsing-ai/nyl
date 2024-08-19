from dataclasses import dataclass, field
from venv import logger

from pathlib import Path

from nyl.tools.fs import find_config_file


@dataclass
class Project:
    """
    Configuration for a Nyl project that is stored in a `nyl-project.toml` file.
    """

    generate_applysets: bool = False
    """
    If enabled, automatically generate an ApplySet for every template file. The applyset will be named after the
    template file, unless there is namespace defined in the template file, in which case the applyset will be named
    after the namespace.
    """

    search_path: list[Path] = field(default_factory=list)
    """
    Search path for additional resources used by the project. Used for example when using the `chart.path` option on a
    `HelmChart` resource.
    """


@dataclass
class ProjectConfig:
    """
    Wrapper for the project configuration file.
    """

    FILENAME = "nyl-project.yaml"

    file: Path | None
    config: Project

    @staticmethod
    def load(file: Path | None = None, /) -> "ProjectConfig":
        """
        Load the project configuration from the given or the default configuration file. If the configuration file does
        not exist, a default project configuration is returned.
        """

        from databind.json import load as deser
        from yaml import safe_load

        if file is None:
            file = find_config_file(ProjectConfig.FILENAME, required=False)
        if file is None:
            return ProjectConfig(None, Project())

        logger.debug("Loading project configuration from '{}'", file)
        project = deser(safe_load(file.read_text()), Project, filename=str(file))

        for idx, path in enumerate(project.search_path):
            if not path.is_absolute():
                path = file.parent / path
                project.search_path[idx] = path
            if not path.exists():
                logger.warning("Search path '{}' does not exist", path)

        return ProjectConfig(file, project)
