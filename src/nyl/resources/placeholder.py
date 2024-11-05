from dataclasses import dataclass
from typing import Annotated, ClassVar

from databind.core import SerializeDefaults

from nyl.resources import API_VERSION_K8S, NylResource, ObjectMetadata


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
