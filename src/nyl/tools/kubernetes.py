from loguru import logger
from kubernetes.dynamic import DynamicClient
from kubernetes.client.api_client import ApiClient


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
