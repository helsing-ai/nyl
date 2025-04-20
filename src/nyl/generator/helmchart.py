import hashlib
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PosixPath
from tempfile import TemporaryDirectory
from textwrap import indent
from urllib.parse import parse_qs, urlparse

from loguru import logger

from nyl.generator import Generator
from nyl.resources.helmchart import ChartRef, HelmChart, ReleaseMetadata
from nyl.tools import yaml
from nyl.tools.kubernetes import populate_namespace_to_resources
from nyl.tools.shell import pretty_cmd
from nyl.tools.types import Manifests

ChartRepositoryVersion = tuple[str | None, str | None, str | None]


@dataclass
class HelmChartGenerator(Generator[HelmChart], resource_type=HelmChart):
    git_repo_cache_dir: Path
    """ A directory that Git repositories are cloned into. """

    chart_cache_dir: Path
    """ A directory where Helm charts are cached."""

    search_path: list[Path]
    """ A list of directories to search for Helm charts in if the chart path is not explicitly absolute or relative. """

    working_dir: Path
    """ The working directory to consider relative paths relative to. """

    kube_version: str
    """
    The Kubernetes API version to generate manifests for. This must be known for Helm cluster feature detection (such
    as, for example, picking the right apiVersion for Ingress resources).
    """

    api_versions: set[str]
    """
    A set of `Capabilities.APIVersions` to pass to the `helm template` function. This must be a complete set to ensure
    the latest capabilities can be used by the Helm chart. Helm would usually look this up automatically with the
    `--validate` flag.
    """

    def _materialize_chart(self, chart_ref: ChartRef) -> ChartRepositoryVersion:
        repository: str | None = None
        chart: str | None = None

        if chart_ref.repository:
            if chart_ref.path:
                raise ValueError("Cannot specify both `chart.repository` and `chart.path`.")
            if chart_ref.git:
                raise ValueError("Cannot specify both `chart.repository` and `chart.git`.")
            if not chart_ref.name:
                raise ValueError("`chart.name` must be set when `chart.repository` is set.")

            if chart_ref.repository.startswith("oci://"):
                chart = f"{chart_ref.repository}/{chart_ref.name}"
            else:
                chart = chart_ref.name
                repository = chart_ref.repository

            parsed = urlparse(chart_ref.repository)
            cache_dir = (
                self.chart_cache_dir
                / f"{parsed.scheme}-{parsed.hostname}-{(parsed.path.replace('/', '-') + '-' + chart).lstrip('-')}"
            )
            command = ["helm", "pull", chart]
            if repository:
                command.extend(["--repo", repository])
            if chart_ref.version:
                command.extend(["--version", chart_ref.version, "--devel"])
                cache_dir = cache_dir / chart_ref.version
            else:
                cache_dir = cache_dir / "latest"

            # TODO: Optimize the cache layout (we can determine the final filename if we have a version, otherwise
            #       we could consider querying the repository or allow for some kind of chartPullPolicy.
            if not cache_dir.is_dir() or not any(cache_dir.iterdir()):
                cache_dir.mkdir(parents=True, exist_ok=True)
                logger.opt(colors=True).debug(
                    "Pulling Helm chart '{}' from repository '{}' with command $ <yellow>{}</>",
                    chart,
                    repository,
                    pretty_cmd(command),
                )
                logger.opt(colors=True).trace("Using cache directory <yellow>{}</>", cache_dir)
                subprocess.check_call(command, cwd=cache_dir, stdout=sys.stderr)
            else:
                logger.opt(colors=True).debug("Using cached Helm chart '{}' from repository '{}'", chart, repository)

            chart = str(next(cache_dir.iterdir()))
            repository = None

        elif chart_ref.git:
            if chart_ref.name:
                raise ValueError("Cannot specify both `chart.git` and `chart.name`, did you mean `chart.path`?")

            # Clone the repository and find the chart in the repository.
            parsed = urlparse(chart_ref.git)
            without_query_params = parsed._replace(query="").geturl()
            hashed = hashlib.md5(without_query_params.encode()).hexdigest()
            clone_dir = self.git_repo_cache_dir / f"{hashed}-{PosixPath(parsed.path).name}"
            if clone_dir.exists():
                logger.debug("Using cached clone of {} at {}", without_query_params, clone_dir)
                command = ["git", "fetch", "--tags"]
                cwd = clone_dir
            else:
                logger.debug("Cloning {} to {}", without_query_params, clone_dir)
                command = ["git", "clone", without_query_params, str(clone_dir)]
                cwd = None
            subprocess.check_call(command, cwd=cwd, stdout=sys.stderr)

            # todo: What if multiple HelmCharts refer to the same directory? Probably better to have a
            #       worktree per instance that refers to a ref of the repository.
            query = parse_qs(parsed.query)
            if "ref" in query:
                logger.debug("Checking out ref {}", query["ref"][0])
                command = ["git", "checkout", query["ref"][0]]
                subprocess.check_call(command, cwd=clone_dir, stdout=sys.stderr)

            chart = str(clone_dir / (chart_ref.path or ""))

        elif chart_ref.path:
            is_explicit = chart_ref.path.startswith("/") or chart_ref.path.startswith("./")
            if not is_explicit:
                for path in self.search_path:
                    chart_path = path / chart_ref.path
                    if chart_path.exists():
                        chart = str(chart_path)
                        break
                else:
                    raise ValueError(f"Chart '{chart_ref.path}' not found in search path {self.search_path}")
            else:
                chart_path = self.working_dir / chart_ref.path
                if not chart_path.exists():
                    raise ValueError(f"Chart path '{chart_ref.path}' not found")
                chart = str(chart_path)

        else:
            raise ValueError("Either `chart.repository`, `chart.git` or `chart.path` must be set.")

        return (repository, chart, chart_ref.version)

    # Generator

    def generate(self, /, res: HelmChart) -> Manifests:
        repository, chart, version = self._materialize_chart(res.spec.chart)
        release = res.spec.release or ReleaseMetadata(name=res.metadata.name, namespace=res.metadata.namespace)

        with TemporaryDirectory() as tmp:
            values_file = Path(tmp) / "values.yaml"
            values_file.write_text(yaml.dumps(res.spec.values))

            command = [
                "helm",
                "template",
                "--debug",
                "--skip-tests",
                "--include-crds",
                "--kube-version",
                self.kube_version,
                # Similar to ArgoCD, we always consider all runs as upgrades. This does impact fresh installs in that
                # some resources may not be created, but it's better to be consistent with ArgoCD and in general it's
                # the better compromise.
                "--is-upgrade",
                # Permit server connections for Helm lookup.
                "--dry-run=server",
                # We cannot use --validate because we would like users to be able generate Nyl inline resources that
                # are not actually installed Kubernetes CRDs, as well as generating custom resources before they are
                # installed.
                # "--validate",
                "--api-versions",
                ",".join(sorted(self.api_versions)),
            ]
            if repository:
                command.extend(["--repo", repository])
            if version:
                command.extend(["--version", version, "--devel"])

            # Note: Support deprecated field `hooksEnabled` for a while.
            if res.spec.options.noHooks:
                command.append("--no-hooks")

            command.extend(["--values", str(values_file)])
            if release.namespace:
                command.extend(["--namespace", release.namespace])
            command.extend(res.spec.options.additionalArgs)
            command.extend([release.name, str(chart)])

            # for key, value in res.set.items():
            #     command.append("--set")
            #     command.append(f"{key}={json.dumps(value)}")

            logger.opt(colors=True).debug(
                "Generating manifests with Helm: $ <yellow>{}</>", " ".join(map(shlex.quote, command))
            )
            try:
                result = subprocess.run(command, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                prefix = "    "
                raise ValueError(
                    f"Failed to generate manifests using Helm.\n{indent(str(e), prefix)}\n"
                    f"stdout:\n{indent(e.stdout.decode(), prefix)}\n"
                    f"stderr:\n{indent(e.stderr.decode(), prefix)}"
                )

            manifests = Manifests(list(filter(None, yaml.loads_all(result.stdout.decode()))))

            if release.namespace:
                populate_namespace_to_resources(manifests, release.namespace)

            for resource in manifests:
                resource["metadata"].setdefault("labels", {}).update(res.metadata.labels or {})

            return manifests
