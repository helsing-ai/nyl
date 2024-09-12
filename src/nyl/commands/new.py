"""
Bootstrap files for a new Nyl project or Helm chart.
"""

from enum import Enum
from pathlib import Path
from textwrap import dedent

from loguru import logger
from typer import Option
from nyl.project.config import ProjectConfig
from nyl.tools.typer import new_typer

app = new_typer(name="new", help=__doc__)


class ComponentType(Enum):
    Helm = "helm"


def _write_file_dedent(dir: Path, name: str, content: str) -> None:
    path = dir.joinpath(name)
    if path.exists():
        logger.warning("File already exists: {}", path)
        return
    logger.info("Writing {}", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip())


@app.command()
def chart(dir: Path) -> None:
    """
    Similar to `helm create`, but generates a much simpler template.
    """

    dir.mkdir(parents=True, exist_ok=True)

    _write_file_dedent(
        dir,
        "Chart.yaml",
        f"""
        apiVersion: v2
        name: {dir.name}
        version: '0.0.0'
        """,
    )

    _write_file_dedent(
        dir,
        "values.yaml",
        """
        image: my/image:tag
        """,
    )

    _write_file_dedent(
        dir,
        "values.schema.json",
        """
        {
            "$schema": "https://json-schema.org/draft/2020-12/output/schema",
            "type": "object",
            "required": [
                "image"
            ],
            "properties": {
                "image": {
                    "type": "string"
                }
            }
        }
        """,
    )

    _write_file_dedent(
        dir,
        "templates/deployment.yaml",
        """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
            name: {{ .Release.Name }}
        spec:
            replicas: 1
            selector:
            matchLabels:
                app: {{ .Release.Name }}
            template:
            metadata:
                labels:
                app: {{ .Release.Name }}
            spec:
                containers:
                - name: {{ .Release.Name }}
                image: {{ .Values.image }}
        """,
    )


@app.command()
def component(
    api_version: str,
    kind: str,
    type: ComponentType = Option("helm", help="The type of Nyl component to create."),
) -> None:
    """Create the boilerplate for a Nyl component in the components directory."""

    components_path = ProjectConfig.load().get_components_path()
    chart(components_path / api_version / kind)
