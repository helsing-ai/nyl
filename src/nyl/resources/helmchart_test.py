from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import pytest

from nyl.resources import ObjectMetadata
from nyl.resources.helmchart import HelmChart, HelmChartSpec, ChartRef
from nyl.generator.helmchart import HelmChartGenerator


@pytest.fixture
def helmchart() -> Iterator[HelmChart]:
    with TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)
        chart_path = tmpdir / "chart"
        chart_path.mkdir()
        (chart_path / "Chart.yaml").write_text(
            """
apiVersion: v2
name: mychart
version: 0.1.0
"""
        )
        (chart_path / "values.yaml").write_text(
            """
replicaCount: 1
"""
        )
        (chart_path / "templates").mkdir()
        (chart_path / "templates" / "deployment.yaml").write_text(
            """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mychart
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: mychart
          image: nginx
"""
        )
        yield HelmChart(
            metadata=ObjectMetadata(name="mychart"),
            spec=HelmChartSpec(
                chart=ChartRef(path=str(chart_path)),
                values={"replicaCount": 2},
            ),
        )


@pytest.fixture
def generator() -> Iterator[HelmChartGenerator]:
    with TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)
        yield HelmChartGenerator(
            git_repo_cache_dir=tmpdir / "git_repo_cache",
            chart_cache_dir=tmpdir / "chart_cache",
            search_path=[],
            working_dir=tmpdir / "working_dir",
            kube_version="1.31",
            api_versions=set(),
        )


def test__HelmChartGenerator__generate__populates_namespace(
    helmchart: HelmChart,
    generator: HelmChartGenerator,
) -> None:
    helmchart.metadata.namespace = None
    manifests = generator.generate(helmchart)
    assert len(manifests) == 1
    assert manifests[0]["metadata"].get("namespace") is None

    helmchart.metadata.namespace = "foo"
    manifests = generator.generate(helmchart)
    assert len(manifests) == 1
    assert manifests[0]["metadata"].get("namespace") == "foo"
