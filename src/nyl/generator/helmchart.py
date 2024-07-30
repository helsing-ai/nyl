from dataclasses import dataclass
import hashlib
from pathlib import Path, PosixPath
import shlex
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

from loguru import logger
import yaml
from nyl.generator import Generator
from nyl.resources.helmchart import HelmChart
from nyl.tools.types import Manifests


@dataclass
class HelmChartGenerator(Generator[HelmChart], resource_type=HelmChart):
    git_repo_cache_dir: Path
    """ A directory that Git repositories are cloned into. """

    search_path: list[Path]
    """ A list of directories to search for Helm charts in if the chart path is not explicitly absolute or relative. """

    working_dir: Path
    """ The working directory to consider relative paths relative to. """

    def generate(self, /, res: HelmChart) -> Manifests:
        repository: str | None = None
        chart: str | None = None

        if res.chart.repository:
            if res.chart.path:
                raise ValueError("Cannot specify both `chart.repository` and `chart.path`.")
            if res.chart.git:
                raise ValueError("Cannot specify both `chart.repository` and `chart.git`.")
            if not res.chart.name:
                raise ValueError("`chart.name` must be set when `chart.repository` is set.")

            if res.chart.repository.startswith("oci://"):
                chart = f"{res.chart.repository}/{res.chart.name}"
            else:
                chart = res.chart.name
                repository = res.chart.repository

        elif res.chart.git:
            # Clone the repository and find the chart in the repository.
            parsed = urlparse(res.chart.git[len("git+") :])
            without_query_params = parsed._replace(query="").geturl()
            hashed = hashlib.md5(without_query_params.encode()).hexdigest()
            clone_dir = self.git_repo_cache_dir / f"{hashed}-{PosixPath(parsed.path).name}"
            if clone_dir.exists():
                logger.info("Using cached clone of {} at {}", without_query_params, clone_dir)
                command = ["git", "fetch", "--tags"]
                cwd = clone_dir
            else:
                logger.info("Cloning {} to {}", without_query_params, clone_dir)
                command = ["git", "clone", without_query_params, str(clone_dir)]
                cwd = None
            subprocess.check_call(command, cwd=cwd)

            # todo: What if multiple HelmCharts refer to the same directory? Probably better to have a
            #       worktree per instance that refers to a ref of the repository.
            query = parse_qs(parsed.query)
            if "ref" in query:
                logger.info("Checking out ref {}", query["ref"][0])
                command = ["git", "checkout", query["ref"][0]]
                subprocess.check_call(command, cwd=clone_dir)

            chart = str(clone_dir / (res.chart.path or ""))

        elif res.chart.path:
            is_explicit = res.chart.path.startswith("/") or res.chart.path.startswith("./")
            if not is_explicit:
                for path in self.search_path:
                    chart_path = path / res.chart.path
                    if chart_path.exists():
                        break
                else:
                    raise ValueError(f"Chart '{res.chart.path}' not found in search path {self.search_path}")
            else:
                chart_path = self.working_dir / res.chart.path
                if not chart_path.exists():
                    raise ValueError(f"Chart path '{res.chart.path}' not found")

            chart = str(chart_path)

        else:
            print(self)
            raise ValueError("Either `chart.repository`, `chart.git` or `chart.path` must be set.")

        # if repository and repository.startswith("nyl://"):
        #     # Find in the Nyl packages index.
        #     assert isinstance(chart, str)
        #     chart = project.find_package((repository[len("nyl://") :] + "/@charts/" + chart).lstrip("/"))

        with TemporaryDirectory() as tmp:
            values_file = Path(tmp) / "values.yaml"
            values_file.write_text(yaml.dump(res.values))

            command = ["helm", "template", "--debug"]
            if repository:
                command.extend(["--repo", repository])
            if res.chart.version:
                command.extend(["--version", res.chart.version, "--devel"])
            command.extend(["--values", str(values_file)])
            if res.release.namespace:
                command.extend(["--namespace", res.release.namespace])
            command.extend([res.release.name or res.name, str(chart)])

            # for key, value in res.set.items():
            #     command.append("--set")
            #     command.append(f"{key}={json.dumps(value)}")

            logger.info("Generating manifests with Helm: $ {}", " ".join(map(shlex.quote, command)))
            try:
                result = subprocess.run(command, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                raise ValueError(f"Failed to get manifests: {e}\n\nstdout: {e.stdout}\n\nstderr: {e.stderr}")

            manifests = Manifests(list(filter(None, yaml.safe_load_all(result.stdout.decode()))))

            return manifests
