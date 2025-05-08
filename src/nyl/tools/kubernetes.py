from loguru import logger

from kubernetes.client.api_client import ApiClient
from kubernetes.dynamic import DynamicClient
from nyl.tools.types import Resource


def discover_kubernetes_api_versions(client: ApiClient) -> set[str]:
    """
    Discover all API versions from the given Kubernetes API client.
    """

    logger.debug("Discovering Kubernetes API versions ...")
    dynamic = DynamicClient(client)
    all_versions = set()
    for resource in dynamic.resources.search():
        all_versions.add(f"{resource.group_version}/{resource.kind}")
    logger.info("Discovered {} Kubernetes API version(s).", len(all_versions))
    return all_versions


def resource_locator(manifest: Resource) -> str:
    """
    Create a string that contains the apiVersion, kind, namespace and name of a Kubernetes resource formatted as

        apiVersion/kind/namespace/name

    This can be used to uniquely identify a resource.
    """

    return (
        f"{manifest['apiVersion']}/{manifest['kind']}/"
        f"{manifest['metadata'].get('namespace', '')}/{manifest['metadata']['name']}"
    )


def populate_namespace_to_resources(resources: list[Resource], namespace: str) -> None:
    """
    Populate the `namespace` field of all resources that don't have it, excluding those that are cluster-scoped.

    Note that the heuristics for determining which resource kind is cluster-scoped is lackluster, check
    :meth:`is_cluster_scoped_resource` for details.
    """

    for resource in resources:
        if (
            "metadata" in resource
            and "namespace" not in resource["metadata"]
            and not is_cluster_scoped_resource(resource)
        ):
            resource["metadata"]["namespace"] = namespace


def drop_empty_metadata_labels(resources: list[Resource]) -> None:
    """
    Drop the `metadata.labels` field from all resources that have it but are empty.

    This gets applied to resources after templating as it can cause the resources to be OutOfSync immediately
    after apply as the Kubernetes API stores the empty labels as `null` instead of `{}`.
    """

    for resource in resources:
        if "metadata" in resource and "labels" in resource["metadata"]:
            if not resource["metadata"]["labels"]:
                del resource["metadata"]["labels"]


def is_cluster_scoped_resource(manifest: Resource) -> bool:
    """
    Check if a manifest is a cluster scoped resource.
    """

    # HACK: We should probably just list the resources via the Kubectl API?
    fqn = manifest.get("kind", "") + "." + manifest.get("apiVersion", "").split("/")[0]
    return fqn in {
        "ClusterRole.rbac.authorization.k8s.io",
        "ClusterRoleBinding.rbac.authorization.k8s.io",
        "CustomResourceDefinition.apiextensions.k8s.io",
        "IngressClass.networking.k8s.io",
        "Namespace.v1",
        "StorageClass.storage.k8s.io",
        "ValidatingWebhookConfiguration.admissionregistration.k8s.io",
    }
