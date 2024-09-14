from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

from nyl.profiles.config import LocalKubeconfig, Profile, ProfileConfig
from nyl.tools.testing import create_files


def test__ProfilesConfig__load__prefers_closer_project_configuration() -> None:
    """When the project configuration is closer than the profiles configuration and configures profiles, it is used."""

    with TemporaryDirectory() as tmp:
        create_files(
            tmp,
            {
                "nyl-profiles.yaml": dedent("""
                    default:
                        kubeconfig:
                            type: local
                """),
                "main/nyl-project.yaml": dedent("""
                    profiles:
                        default:
                            kubeconfig:
                                type: local
                                context: main
                """),
            },
        )

        profiles = ProfileConfig.load(cwd=Path(tmp) / "main")
        assert profiles == ProfileConfig(
            file=Path(tmp) / "main" / "nyl-project.yaml",
            profiles={"default": Profile(kubeconfig=LocalKubeconfig(context="main"))},
        )


def test__ProfilesConfig__load__skips_project_configuration_if_no_profiles_configured() -> None:
    """When there is a project configuration but it does not configure any profiles, the profiles configuration is used."""

    with TemporaryDirectory() as tmp:
        create_files(
            tmp,
            {
                "nyl-profiles.yaml": dedent("""
                    default:
                        kubeconfig:
                            type: local
                """),
                "main/nyl-project.yaml": dedent("""
                    profiles: {}
                """),
            },
        )

        profiles = ProfileConfig.load(cwd=Path(tmp) / "main")
        assert profiles == ProfileConfig(
            file=Path(tmp) / "nyl-profiles.yaml",
            profiles={"default": Profile(kubeconfig=LocalKubeconfig())},
        )
