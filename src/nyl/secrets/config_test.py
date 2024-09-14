from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

from nyl.secrets.config import SecretsConfig
from nyl.secrets.sops import SopsFile
from nyl.tools.testing import create_files


def test__SecretsConfig__load__prefers_closer_project_configuration() -> None:
    """When the project configuration is closer than the secrets configuration and configures secrets, it is used."""

    with TemporaryDirectory() as tmp:
        create_files(
            tmp,
            {
                "nyl-secrets.yaml": dedent("""
                    default:
                        type: sops
                        path: secrets.yaml
                """),
                "main/nyl-project.yaml": dedent("""
                    secrets:
                        default:
                            type: sops
                            path: secrets.yaml
                """),
            },
        )

        secrets = SecretsConfig.load(cwd=Path(tmp) / "main")
        assert secrets == SecretsConfig(
            file=Path(tmp) / "main" / "nyl-project.yaml",
            providers={"default": SopsFile(path=Path(tmp) / "main" / "secrets.yaml")},
        )


def test__SecretsConfig__load__skips_project_configuration_if_no_secrets_configured() -> None:
    """When there is a project configuration but it does not configure any secrets, the secrets configuration is used."""

    with TemporaryDirectory() as tmp:
        create_files(
            tmp,
            {
                "nyl-secrets.yaml": dedent("""
                    default:
                        type: sops
                        path: secrets.yaml
                """),
                "main/nyl-project.yaml": dedent("""
                    secrets: {}
                """),
            },
        )

        secrets = SecretsConfig.load(cwd=Path(tmp) / "main")
        assert secrets == SecretsConfig(
            file=Path(tmp) / "nyl-secrets.yaml",
            providers={"default": SopsFile(path=Path(tmp) / "secrets.yaml")},
        )
