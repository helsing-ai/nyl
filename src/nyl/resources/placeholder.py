import base64
from dataclasses import dataclass
import hashlib
from typing import Annotated, ClassVar
from nyl.resources import API_VERSION_K8S, NylResource, ObjectMetadata
from databind.core import SerializeDefaults


@dataclass(kw_only=True)
class Placeholder(NylResource, api_version=API_VERSION_K8S):
    """
    A Placeholder is a dummy custom resource that is used to represent a resource that failed to evaluate during
    templating. This is useful when you want to define a manifest that has dependencies on other manifests based on
    `lookup()` calls, but you want to avoid the evaluation of the manifest to fail if the lookup fails.

    The placeholder can inform you that a component of your manifest is missing, and you can then decide how to handle
    the situation.

    Note that removal of Placeholder resources is not handled by Nyl: It will either be pruned as part of a
    reconciliation by ArgoCD (if you're using that) or pruned with ApplySets. If you're not using either of those, you
    will have to manually remove the Placeholder resources.

    A placeholder can contain arbitrary `spec` data and usually contains fields to help you identify the missing
    resource.
    """

    # HACK: Can't set it on the class level, see https://github.com/NiklasRosenstein/python-databind/issues/73.
    metadata: Annotated[ObjectMetadata, SerializeDefaults(False)]

    CRD: ClassVar = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": f"placeholders.{API_VERSION_K8S.split('/')[0]}",
        },
        "spec": {
            "group": API_VERSION_K8S.split("/")[0],
            "names": {
                "kind": "Placeholder",
                "plural": "placeholders",
            },
            "scope": "Namespaced",
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "A message that describes the missing resource.",
                                        },
                                        "reason": {
                                            "type": "string",
                                            "description": "The reason why the resource is missing (e.g. 'NotFound').",
                                        },
                                    },
                                },
                            },
                        }
                    },
                }
            ],
        },
    }

    @staticmethod
    def new(name: str, namespace: str) -> "Placeholder":
        return Placeholder(
            metadata=ObjectMetadata(
                name=name,
                namespace=namespace,
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
