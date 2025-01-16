from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from loguru import logger

from nyl.profiles.config import Profile
from nyl.secrets import SecretProvider
from nyl.tools.di import DependenciesProvider
from nyl.tools.fs import distance_to_cwd, find_config_file
from nyl.tools.loads import loadf


@dataclass
class ProjectSettings:
    """
    Configuration for a Nyl project that is stored in a `nyl-project.yaml` file.
    """

    generate_applysets: bool = False
    """
    If enabled, automatically generate an ApplySet for every template file. The applyset will be named after the
    template file, unless there is namespace defined in the template file, in which case the applyset will be named
    after the namespace.
    """

    generate_placeholders: bool | None = None
    """
    **Deprecated.** Will be removed in a future version. Use `on_lookup_failure` set to `CreatePlaceholder` instead.
    """

    on_lookup_failure: Literal["Error", "CreatePlaceholder", "SkipResource"] = "Error"
    """
    Can be used to tell Nyl to create a placeholder resource (`nyl.io/v1/Placeholder`) or skip a resource that was
    dependant on a `lookup()` call if the lookup fails. Otherwise, the error will be propagated.
    """

    components_path: Path | None = None
    """
    Path to the directory that contains Nyl components.
    """

    search_path: list[Path] = field(default_factory=lambda: [Path(".")])
    """
    Search path for additional resources used by the project. Used for example when using the `chart.path` option on a
    `HelmChart` resource. Relative paths specified here are considered relative to the `nyl-project.yaml` configuration
    file.
    """

    def __post_init__(self) -> None:
        if self.generate_placeholders is not None:
            logger.warning(
                "The 'generate_placeholders' setting is deprecated and will be removed in a future version. "
                "Use 'on_lookup_failure' set to 'CreatePlaceholder' instead."
            )
            if self.generate_placeholders:
                self.on_lookup_failure = "CreatePlaceholder"


@dataclass
class Project:
    """
    A project configuration file _may_ contain profiles and secret settings in addition to what we usually call project
    settings. This it to simplify the configuration in a simple project, to not require up to three separate
    configuration files.

    However, when Nyl loads profiles and secrets configuration, the closest configuration file is used, so a closer
    `nyl-profiles.yaml` or `nyl-secrets.yaml` may override the settings in the `nyl-project.yaml` file. Do note that
    multiple levels of `nyl-project.yaml` files do not stack/merge.
    """

    settings: ProjectSettings = field(default_factory=ProjectSettings)
    """
    Project settings.
    """

    profiles: dict[str, Profile] = field(default_factory=dict)
    """
    Profiles configuration. You may also configure these in a separate `nyl-profiles.yaml` file.
    """

    secrets: dict[str, SecretProvider] = field(default_factory=dict)
    """
    Secrets configuration. You may also configure these in a separate `nyl-secrets.yaml` file.
    """


@dataclass
class ProjectConfig:
    """
    Wrapper for the project configuration file.
    """

    FILENAMES = ["nyl-project.yaml", "nyl-project.toml", "nyl-project.json"]

    file: Path | None
    config: Project

    def get_components_path(self) -> Path:
        return (self.file.parent if self.file else Path.cwd()) / (self.config.settings.components_path or "components")

    @staticmethod
    def find(cwd: Path | None = None) -> Path | None:
        """
        Find the project configuration file in the current directory or any parent directory. The configuration, if
        any, can be loaded with [`ProjectConfig.load()`].
        """

        return find_config_file(ProjectConfig.FILENAMES, cwd, required=False)

    @staticmethod
    def load(
        file: Path | None = None,
        /,
        *,
        dependencies: DependenciesProvider | None = None,
        init_secret_providers: bool = True,
    ) -> "ProjectConfig":
        """
        Load the project configuration from the given or the default configuration file. If the configuration file does
        not exist, a default project configuration is returned.

        Args:
            file: The file to loads the project configuration from. If not specified, the file is automatically
                discovered using :meth:`ProjectConfig.find()` by traversing the filesystem hierarchy. If no file is
                found, an empty project configuration will be returned.
            dependencies: A dependency provider for the initialization of the :class:`SecretProvider`s defined in the
                project. If not specified, an empty provider is used, but this may mean not all implementations of
                :class:`SecretProvider` can be used.
            init_secret_providers: Whether to initialize secret providers. Usually this should be left enabled, but
                for cases where you're not interested in the providers, you can turn this off.
        """

        from databind.json import load as deser

        if file is None:
            file = ProjectConfig.find()

        if file is None:
            return ProjectConfig(None, Project())

        logger.debug("Loading project configuration from '{}'", file)
        project = deser(loadf(file), Project, filename=str(file))

        # Make sure search paths are absolute, relative to the configuration file parent directory.
        for idx, path in enumerate(project.settings.search_path):
            if not path.is_absolute():
                path = file.parent / path
                project.settings.search_path[idx] = path
            if not path.exists():
                logger.warning("Search path '{}' does not exist", path)

        # Make sure the secrets are initialized.
        if init_secret_providers:
            if dependencies is None:
                dependencies = DependenciesProvider.default()
            for provider in project.secrets.values():
                provider.init(file, dependencies)

        return ProjectConfig(file, project)

    @staticmethod
    def load_if_has_precedence(
        *,
        over: Path | None,
        cwd: Path | None = None,
        predicate: Callable[["ProjectConfig"], bool],
        dependencies: DependenciesProvider | None = None,
        init_secret_providers: bool = True,
    ) -> "ProjectConfig | None":
        """
        Load the project configuration if it takes precedence over the given configuration file and the project
        fulfills the given predicate.

        Args:
            over: Path to the configuration file that the project configuration may take precedence over. The
                precedence is determined by the distance to the current working directory (the closer file takes it).
                In addition to the locality of the file, the project configuration must also satisfy the given
                predicate to have precedence.

                If this is `None`, the project configuration is always used if it is found, but it must still satisfy
                the predicate.
            cwd: The current working directory. Defaults to the current working directory.
            predicate: The predicate that the project configuration must satisfy to take precedence. This is checked
                if the project configuration file is closer than the given configuration file.
            dependencies: See :meth:`ProjectConfig.load`.
            init_secret_providers: See :meth:`ProjectConfig.load`.

        Returns:
            The project configuration if it takes precedence and satisfies the predicate, otherwise `None`.
        """

        config_file = ProjectConfig.find(cwd)
        if not config_file:
            return None

        if over:
            logger.trace("Checking if project configuration '{}' takes precedence over '{}'", config_file, over)
            # We always only check files based on the current working directory or its parent directories. Thus, we
            # only want to consider precedence if distance_to_cwd() returns 0 or a negative number, hence if the
            # distance is lower to that of the current working directory, it is farther away and should not take
            # precedence.
            if distance_to_cwd(config_file.parent, cwd) >= abs(distance_to_cwd(over.parent, cwd)):
                return None

            logger.trace("Project configuration '{}' is closer to '{}' than '{}'", config_file, cwd, over)

        project = ProjectConfig.load(
            config_file, dependencies=dependencies, init_secret_providers=init_secret_providers
        )
        if predicate(project):
            logger.trace("Project configuration '{}' takes precedence", config_file)
            return project
        else:
            logger.trace("Project configuration '{}' does not satisfy the predicate", config_file)

        return None
