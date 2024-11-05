from loguru import logger

from kubernetes.client.api_client import ApiClient
from kubernetes.dynamic import DynamicClient
from nyl.tools.types import Manifest


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


def resource_locator(manifest: Manifest) -> str:
    """
    Create a string that contains the apiVersion, kind, namespace and name of a Kubernetes resource formatted as

        apiVersion/kind/namespace/name

    This can be used to uniquely identify a resource.
    """

    return (
        f"{manifest['apiVersion']}/{manifest['kind']}/"
        f"{manifest['metadata'].get('namespace', '')}/{manifest['metadata']['name']}"
    )
