from dataclasses import dataclass, field
from typing import Any

from nyl.resources import API_VERSION_INLINE, NylResource, ObjectMetadata


@dataclass
class ChartRef:
    """
    Represents a reference to a Helm chart.
    """

    path: str | None = None
    """
    Path to the chart in the Git repository; or relative to the file that defines the resource. This path is
    searched in the [`Project`] search path.
    """

    git: str | None = None
    """ URL to a Git repository containing the chart. May include a query string to specify a `ref` or `rev`. """

    repository: str | None = None
    """ A Helm repository, if the chart is not local. Must either use the `https://` or `oci://` scheme. """

    name: str | None = None
    """ The name of the chart. This is only needed when `repository` is set. """

    version: str | None = None
    """ The version of the chart. This is only needed when `repository` is set. """


@dataclass
class ReleaseMetadata:
    """
    Metadata for a Helm release.
    """

    name: str
    """ The name of the release. If not set, the name of the Helm chart resource is used. """

    namespace: str | None = None
    """ The namespace where the release should be installed. """


@dataclass
class ChartOptions:
    additionalArgs: list[str] = field(default_factory=list)
    """Escape hatch for passing arbitrary arguments to `helm template`."""

    noHooks: bool = False
    """
    If set to `True`, oass the `--no-hooks` option to `helm template`.

    When rendering templates with Nyl, just like ArgoCD, it cannot make Helm aware of a previous installation. To
    quote the ArgoCD documentation:

    > Argo CD cannot know if it is running a first-time "install" or an "upgrade" - every operation is a "sync'.
    > This means that, by default, apps that have pre-install and pre-upgrade will have those hooks run at the same
    > time.
    """


@dataclass(kw_only=True)
class HelmChartSpec:
    chart: ChartRef
    """ Reference to the Helm chart. """

    release: ReleaseMetadata | None = None
    """ Override the Helm release options. Defaults to the resource metadata. """

    options: ChartOptions = field(default_factory=ChartOptions)
    """ Helm template options. """

    values: dict[str, Any] = field(default_factory=dict)
    """ Values for the Helm chart. """


@dataclass(kw_only=True)
class HelmChart(NylResource, api_version=API_VERSION_INLINE):
    """
    Represents a Helm chart.
    """

    metadata: ObjectMetadata
    """
    The helm chart metadata. Note that the labels and annotations are not used. The `name` and `namespae` serve as
    the release name and namespace, respectively.
    """

    spec: HelmChartSpec
    """ The Helm chart specification. """
