"""
Convenient CLI for making ammends to Kubernetes manifest files.
"""

from pathlib import Path
import sys
from typer import Argument, Option, Typer
from loguru import logger
import yaml

from nyl.commands.template import (
    DEFAULT_NAMESPACE_ANNOTATION,
    ManifestsWithSource,
    is_namespace_resource,
    load_manifests,
)
from nyl.tools.typer import new_typer


app: Typer = new_typer(name="add", help=__doc__)


@app.command()
def namespace(
    manifest: Path = Option(..., "-m", "--manifest", help="The manifest YAML file to add the namespace to."),
    name: str = Argument(help="Name of the namespace to add."),
) -> None:
    """
    Add a Kubernetes `Namespace` resource definition to the top of the specified manifest file.

    If this is the first namespace defined in the manifest, it will be annotated with `nyl.io/default-namespace`.
    """

    if manifest.exists():
        content = manifest.read_text()
        resources = load_manifests([manifest])[0]
    else:
        content = ""
        resources = ManifestsWithSource([], manifest)

    if any(is_namespace_resource(x) and x["metadata"]["name"] == name for x in resources.manifests):
        logger.error("Namespace '{}' already exists in {}.", name, manifest)
        sys.exit(1)

    namespace = {
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
