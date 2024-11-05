import base64
import hashlib
from dataclasses import dataclass
from typing import Annotated, ClassVar

from databind.core import SerializeDefaults

from nyl.resources import API_VERSION_K8S, NylResource, ObjectMetadata
from nyl.tools.types import Manifests

APPLYSET_LABEL_PART_OF = "applyset.kubernetes.io/part-of"
""" Label key to use to associate objects with an ApplySet resource. """

APPLYSET_LABEL_ID = "applyset.kubernetes.io/id"
""" Label key to use on ApplySet resources to identify it. """

APPLYSET_ANNOTATION_TOOLING = "applyset.kubernetes.io/tooling"
""" Annotation key to use on ApplySet resources to specify the tooling used to apply the ApplySet. """

APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS = "applyset.kubernetes.io/contains-group-kinds"
""" Annotation key to use on ApplySet resources to specify the kinds of resources that are part of the ApplySet. """


@dataclass(kw_only=True)
class ApplySet(NylResource, api_version=API_VERSION_K8S):
    """
    An ApplySet functions as a grouping mechanism for a set of objects that are applied together. This is a standard
    Kubernetes mechanism that needs to be implemented as a custom resource. To read more about ApplySets, check out the
    following article:

        https://kubernetes.io/blog/2023/05/09/introducing-kubectl-applyset-pruning/

    Nyl's ApplySet resource is not namespaces.

    When loading manifests from a file, Nyl looks for an ApplySet resource to determine if the manifests are to be
    associated with an ApplySet.
    """

    # HACK: Can't set it on the class level, see https://github.com/NiklasRosenstein/python-databind/issues/73.
    metadata: Annotated[ObjectMetadata, SerializeDefaults(False)]

    # note: the only purpose of this CRD is to create resources that act as a parent for ApplySets.
    #       check out this GitHub issue, and specifically this comment for more information:
    #       https://github.com/kubernetes/enhancements/issues/3659#issuecomment-1753091733
    CRD: ClassVar = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": f"applysets.{API_VERSION_K8S.split('/')[0]}",
            "labels": {
                "applyset.kubernetes.io/is-parent-type": "true",
            },
        },
        "spec": {
            "group": API_VERSION_K8S.split("/")[0],
            "names": {
                "kind": "ApplySet",
                "plural": "applysets",
            },
            "scope": "Cluster",
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                        }
                    },
                }
            ],
        },
    }

    @property
    def reference(self) -> str:
        """
        Return the refernce to this ApplySet resource that can be given to the `--applyset` flag of `kubectl apply`.
        """

        return f"applysets.{self.API_VERSION.split('/')[0]}/{self.metadata.name}"

    @property
    def id(self) -> str | None:
        """
        Returns the ID of the ApplySet as it is configured in the `applyset.kubernetes.io/id` label.
        """

        if self.metadata.labels is not None:
            return self.metadata.labels.get(APPLYSET_LABEL_ID)
        return None

    @id.setter
    def id(self, value: str) -> None:
        """
        Set the ID of the ApplySet.
        """

        if self.metadata.labels is None:
            self.metadata.labels = {}
        self.metadata.labels[APPLYSET_LABEL_ID] = value

    def calculate_id(self) -> str:
        """
        Calculate the ID of the ApplySet based on the name and namespace of the ApplySet.
        """

        return calculate_applyset_id(
            name=self.metadata.name, namespace=self.metadata.namespace or "", group=self.API_VERSION.split("/")[0]
        )

    @property
    def tooling(self) -> str | None:
        """
        Returns the tooling that was used to apply the ApplySet.
        """

        if self.metadata.annotations is not None:
            return self.metadata.annotations.get(APPLYSET_ANNOTATION_TOOLING)
        return None

    @tooling.setter
    def tooling(self, value: str) -> None:
        """
        Set the tooling that was used to apply the ApplySet.
        """

        if self.metadata.annotations is None:
            self.metadata.annotations = {}
        self.metadata.annotations[APPLYSET_ANNOTATION_TOOLING] = value

    @property
    def contains_group_kinds(self) -> list[str] | None:
        """
        Returns the kinds of resources that are part of the ApplySet.
        """

        if self.metadata.annotations is not None:
            value = self.metadata.annotations.get(APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS)
            if value is not None:
                return value.split(",")
        return None

    @contains_group_kinds.setter
    def contains_group_kinds(self, value: list[str]) -> None:
        """
        Set the kinds of resources that are part of the ApplySet.
        """

        if self.metadata.annotations is None:
            self.metadata.annotations = {}
        self.metadata.annotations[APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS] = ",".join(sorted(value))

    def set_group_kinds(self, manifests: Manifests) -> None:
        """
        Set the kinds of resources that are part of the ApplySet based on the specified manifests.
        """

        kinds = set()
        for manifest in manifests:
            if "kind" in manifest:
                kinds.add(get_canonical_resource_kind_name(manifest["apiVersion"], manifest["kind"]))
        self.contains_group_kinds = list(kinds)

    def validate(self) -> None:
        """
        Validate the ApplySet configuration.

        Mutations:
            - Sets the `applyset.kubernetes.io/id` label on the metadata of the ApplySet resource if it is not set.

        Raises:
            ValueError:
                - If the resource is namespaced.
                - If the annotations has no `applyset.kubernetes.io/tooling` key.
                - If the annotations has no `applyset.kubernetes.io/contains-group-kinds` key.
                - If the `applyset.kubernetes.io/id` label has an invalid value.
        """

        if self.metadata.namespace:
            raise ValueError("ApplySet resources cannot be namespaced")

        if self.metadata.labels is None:
            self.metadata.labels = {}

        if self.id is None:
            self.id = self.calculate_id()
        elif self.id != self.calculate_id():
            raise ValueError(f"Invalid {APPLYSET_LABEL_ID!r} label value: {self.id!r}")

        if self.tooling is None:
            raise ValueError(f"ApplySet resource must have a {APPLYSET_ANNOTATION_TOOLING!r} annotation")

        if self.contains_group_kinds is None:
            raise ValueError(f"ApplySet resource must have a {APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS!r} annotation")

    @staticmethod
    def new(name: str) -> "ApplySet":
        """
        Create a new ApplySet resource with the specified name.
        """

        return ApplySet(
            metadata=ObjectMetadata(
                name=name,
                namespace=None,
            )
        )


def calculate_applyset_id(*, name: str, namespace: str = "", group: str) -> str:
    """
    Calculate the ID of a Kubernetes ApplySet with the specified name.
    """

    # reference: https://kubernetes.io/docs/reference/labels-annotations-taints/#applyset-kubernetes-io-id
    hash = hashlib.sha256(f"{name}.{namespace}.ApplySet.{group}".encode()).digest()
    uid = base64.b64encode(hash).decode().rstrip("=").replace("/", "_").replace("+", "-")
    return f"applyset-{uid}-v1"


def get_canonical_resource_kind_name(api_version: str, kind: str) -> str:
    """
    Given the apiVersion and kind of a Kubernetes resource, return the canonical name of the resource. This name can
    be used to identify the resource in an ApplySet's `applyset.kubernetes.io/contains-group-kinds` annotation.

    Note that according to the [reference][1], the resource name should use the plural form, but it appears that the
    resource kind name is also accepted. Deriving the plural form will be difficult without querying the Kubernetes
    API.

    [1]: https://kubernetes.io/docs/reference/labels-annotations-taints/#applyset-kubernetes-io-contains-group-kinds

    Args:
        api_version: The apiVersion of the resource.
        kind: The kind of the resource.
    """

    return (f"{kind}." + (api_version.split("/")[0] if "/" in api_version else "")).rstrip(".")
