from dataclasses import dataclass

from nyl.resources import API_VERSION_INLINE, NylResource, ObjectMetadata


@dataclass(kw_only=True)
class StatefulSecret(NylResource, api_version=API_VERSION_INLINE):
    """
    Represents a Kubernetes secret that is stateful, i.e. it won't overwrite existing state in the cluster.
    """

    metadata: ObjectMetadata
    type: str = "Opaque"
    stringData: dict[str, str]
