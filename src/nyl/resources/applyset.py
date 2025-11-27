import base64
import hashlib
from dataclasses import dataclass, field

from nyl.tools.types import Resource, ResourceList

APPLYSET_LABEL_PART_OF = "applyset.kubernetes.io/part-of"
""" Label key to use to associate objects with an ApplySet resource. """

APPLYSET_LABEL_ID = "applyset.kubernetes.io/id"
""" Label key to use on ApplySet resources to identify it. """

APPLYSET_ANNOTATION_TOOLING = "applyset.kubernetes.io/tooling"
""" Annotation key to use on ApplySet resources to specify the tooling used to apply the ApplySet. """

APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS = "applyset.kubernetes.io/contains-group-kinds"
""" Annotation key to use on ApplySet resources to specify the kinds of resources that are part of the ApplySet. """


@dataclass
class ApplySet:
    """
    An ApplySet functions as a grouping mechanism for a set of objects that are applied together. This uses a
    ConfigMap as the parent resource, which is the recommended approach for ApplySets.

    To read more about ApplySets, check out the following article:
        https://kubernetes.io/blog/2023/05/09/introducing-kubectl-applyset-pruning/

    The ApplySet is namespace-scoped (using a ConfigMap) and should be placed in the "default" namespace
    determined by Nyl's namespace resolution logic.

    When loading manifests from a file, Nyl looks for an ApplySet definition to determine if the manifests are to be
    associated with an ApplySet.
    """

    name: str
    namespace: str
    tooling: str = ""
    contains_group_kinds: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """
        Returns the ID of the ApplySet.
        """
        return calculate_applyset_id(name=self.name, namespace=self.namespace)

    def set_group_kinds(self, manifests: ResourceList) -> None:
        """
        Set the kinds of resources that are part of the ApplySet based on the specified manifests.
        """

        kinds = set()
        for manifest in manifests:
            if "kind" in manifest:
                kinds.add(get_canonical_resource_kind_name(manifest["apiVersion"], manifest["kind"]))
        self.contains_group_kinds = sorted(kinds)

    def validate(self) -> None:
        """
        Validate the ApplySet configuration.

        Raises:
            ValueError:
                - If the name is empty.
                - If the namespace is empty.
                - If the tooling is not set.
                - If the contains_group_kinds is empty.
        """

        if not self.name:
            raise ValueError("ApplySet name cannot be empty")

        if not self.namespace:
            raise ValueError("ApplySet namespace cannot be empty")

        if not self.tooling:
            raise ValueError(f"ApplySet must have a {APPLYSET_ANNOTATION_TOOLING!r} annotation")

        if not self.contains_group_kinds:
            raise ValueError(f"ApplySet must have a {APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS!r} annotation")

    def dump(self) -> Resource:
        """
        Dump the ApplySet as a ConfigMap resource with the appropriate annotations and labels.
        """

        return Resource({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "annotations": {
                    APPLYSET_ANNOTATION_TOOLING: self.tooling,
                    APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS: ",".join(self.contains_group_kinds),
                },
                "labels": {
                    APPLYSET_LABEL_ID: self.id,
                },
            },
        })

    @staticmethod
    def new(name: str, namespace: str) -> "ApplySet":
        """
        Create a new ApplySet with the specified name and namespace.
        """

        return ApplySet(name=name, namespace=namespace)


def calculate_applyset_id(*, name: str, namespace: str) -> str:
    """
    Calculate the ID of a Kubernetes ApplySet with the specified name and namespace.
    The ID is based on a ConfigMap parent resource.
    """

    # reference: https://kubernetes.io/docs/reference/labels-annotations-taints/#applyset-kubernetes-io-id
    # Format: applyset-<base64(sha256(<name>.<namespace>.ConfigMap.))>-v1
    hash_input = f"{name}.{namespace}.ConfigMap."
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()
    uid = base64.b64encode(hash_bytes).decode().rstrip("=").replace("/", "_").replace("+", "-")
    return f"applyset-{uid}-v1"


def get_canonical_resource_kind_name(api_version: str, kind: str) -> str:
    """
    Given the apiVersion and kind of a Kubernetes resource, return the canonical name of the resource. This name can
    be used to identify the resource in an ApplySet's `applyset.kubernetes.io/contains-group-kinds` annotation.

    The annotation format is `<Kind>.<Group>` where Kind is the singular, capitalized kind name.
    For core v1 resources (no group), the format is just `<Kind>`.
    See: https://kubernetes.io/docs/reference/labels-annotations-taints/#applyset-kubernetes-io-contains-group-kinds

    Args:
        api_version: The apiVersion of the resource (e.g., 'v1', 'apps/v1', 'argoproj.io/v1alpha1').
        kind: The kind of the resource (e.g., 'Pod', 'Deployment', 'CronWorkflow').

    Returns:
        The canonical resource name in the format '<Kind>.<group>' (e.g., 'Deployment.apps', 'Pod').
    """

    group = api_version.split("/")[0] if "/" in api_version else ""
    return (f"{kind}.{group}").rstrip(".")
