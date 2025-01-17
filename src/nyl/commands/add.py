"""
Convenient CLI for making ammends to Kubernetes manifest files.
"""

from pathlib import Path
import sys
from typing import Any
from typer import Argument, Option, Typer
from loguru import logger
import yaml

from nyl.commands.template import (
    DEFAULT_NAMESPACE_ANNOTATION,
    ManifestsWithSource,
    is_namespace_resource,
    load_manifests,
)
from nyl.resources import ObjectMetadata
from nyl.resources.helmchart import ChartRef, HelmChart, HelmChartSpec
from nyl.tools.typer import new_typer
from nyl.tools.types import Manifests

app: Typer = new_typer(name="add", help=__doc__)

MANIFEST_OPTION = Option(..., "-m", "--manifest", help="The manifest YAML file to add the namespace to.")


@app.command()
def namespace(
    manifest: Path = MANIFEST_OPTION,
    name: str = Argument(help="Name of the namespace to add."),
) -> None:
    """
    Add a Kubernetes `Namespace` resource definition to the top of the specified manifest file.

    If this is the first namespace defined in the manifest, it will be annotated with `nyl.io/is-default-namespace`.
    """

    if manifest.exists():
        content = manifest.read_text()
        resources = load_manifests([manifest])[0]
    else:
        content = ""
        resources = ManifestsWithSource(Manifests([]), manifest)

    if any(is_namespace_resource(x) and x["metadata"]["name"] == name for x in resources.manifests):
        logger.error("Namespace '{}' already exists in {}.", name, manifest)
        sys.exit(1)

    namespace: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": name,
        },
    }

    as_default = not any(is_namespace_resource(x) for x in resources.manifests)
    if as_default:
        namespace["metadata"]["annotations"] = {DEFAULT_NAMESPACE_ANNOTATION: "true"}

    if not content.lstrip().startswith("---"):
        content = f"---\n{content}"
    content = f"---\n{yaml.safe_dump(namespace, sort_keys=False)}\n{content}"
    manifest.write_text(content)

    logger.info("Added {}namespace '{}' to {}.", "default " if as_default else "", name, manifest)


@app.command()
def chart(
    manifest: Path = MANIFEST_OPTION,
    name: str = Argument(help="The release name."),
    namespace: str | None = Option(None, "-n", "--namespace", help="The release namespace."),
    repository: str | None = Option(None, "--repo", "--repository", help="The chart repository."),
    chart: str | None = Option(None, "--chart", help="The chart name."),
    version: str | None = Option(None, "--version", help="The chart version."),
    path: str | None = Option(None, "--path", help="The chart path if consumed from disk."),
    git: str | None = Option(None, "--git", help="Git URL of the chart."),
) -> None:
    """
    Append a Nyl `HelmChart` resource to the specified manifest file.
    """

    if repository or chart or version:
        if not repository or not chart or not version:
            logger.error("If any of --repo, --chart, or --version are specified, all must be specified.")
            sys.exit(1)

        if path or git:
            logger.error("If --repo is specified, --path and --git must not be specified.")
            sys.exit(1)

    if git:
        if repository:
            logger.error("If --git is specified, --repo must not be specified.")
            sys.exit(1)

    resource = HelmChart(
        metadata=ObjectMetadata(name=name, namespace=namespace),
        spec=HelmChartSpec(
            chart=ChartRef(
                path=path,
                git=git,
                repository=repository,
                name=chart,
                version=version,
            ),
            values={},
        ),
    )

    content = manifest.read_text() if manifest.exists() else ""
    if not content.rstrip().endswith("---"):
        content += "\n---\n"
    content += yaml.safe_dump(resource.dump())

    manifest.write_text(content)
