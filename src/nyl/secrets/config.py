from dataclasses import dataclass
from pathlib import Path

from kubernetes.client.api_client import ApiClient
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
    def load(
        file: Path | None = None, /, *, cwd: Path | None = None, api_client: ApiClient | None = None
    ) -> "SecretsConfig":
        """
        Load the secrets configuration from the given or the default configuration file. If the configuration file does
        not exist, a [NullSecretsProvider] is used.

        If no *file* is provided, and a closer [`ProjectConfig`] can be found, the secrets configuration from that file
        is used instead, if it has any. If there is a project configuration without any secrets configuration and
        a less-close secrets configuration file is found, that is used instead.

        Args:
            file: A configuration file that defines zero or more :class:`SecretProvider`s. If not specified, the
                default file will be discovered by traversin the filesystem hierarchy. If no file is found, an empty
                :class:`SecretsConfig` is returned with a :class:`NullSecretsProvider` under the `default` key.
            cwd: The working directory from which to discover the default configuration file if no *file* argument
                is specified or is set to :const:`None`.
            api_client: Optional Kubernetes API client for providers that need cluster access.
        """

        from databind.json import load as deser

        from nyl.project.config import ProjectConfig
        from nyl.secrets.null import NullSecretsProvider

        if file is None:
            file = find_config_file(SecretsConfig.FILENAMES, cwd, required=False)

            # Check if there is a project configuration file that is closed.
            project = ProjectConfig.load_if_has_precedence(
                over=file,
                cwd=cwd,
                predicate=lambda cfg: bool(cfg.config.secrets),
                api_client=api_client,
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
                provider.init(file, api_client)
            return SecretsConfig(file, providers)
