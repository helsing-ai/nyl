from dataclasses import dataclass
from pathlib import Path
from loguru import logger

from nyl.secrets import SecretProvider
from nyl.tools.fs import find_config_file
from nyl.tools.loads import loadf


@dataclass
class SecretsConfig:
    FILENAMES = ["nyl-secrets.yaml", "nyl-secrets.toml", "nyl-secrets.json"]

    file: Path | None
    providers: dict[str, SecretProvider]

    @staticmethod
    def load(file: Path | None = None, /, *, cwd: Path | None = None) -> "SecretsConfig":
        """
        Load the secrets configuration from the given or the default configuration file. If the configuration file does
        not exist, a [NullSecretsProvider] is used.

        If no *file* is provided, and a closer [`ProjectConfig`] can be found, the secrets configuration from that file
        is used instead, if it has any. If there is a project configuration without any secrets configuration and
        a less-close secrets configuration file is found, that is used instead.
        """

        from databind.json import load as deser
        from nyl.secrets.null import NullSecretsProvider
        from nyl.project.config import ProjectConfig

        if file is None:
            file = find_config_file(SecretsConfig.FILENAMES, cwd, required=False)

            # Check if there is a project configuration file that is closed.
            project = ProjectConfig.load_if_has_precedence(
                over=file,
                cwd=cwd,
                predicate=lambda cfg: bool(cfg.config.secrets),
            )
            if project:
                logger.debug("Using secrets from project configuration ({}).", project.file)
                return SecretsConfig(project.file, project.config.secrets)

        if file is None:
            logger.debug("Found no Nyl secrets configuration file.")
            return SecretsConfig(None, {"default": NullSecretsProvider()})
        else:
            logger.debug("Loading secrets configuration from '{}'.", file)
            providers = deser(loadf(file), dict[str, SecretProvider], filename=str(file))
            for provider in providers.values():
                provider.init(file)
            return SecretsConfig(file, providers)
