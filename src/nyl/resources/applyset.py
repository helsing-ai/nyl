import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any
from loguru import logger

from kubernetes.client.api_client import ApiClient
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError

from nyl.tools.types import Resource, ResourceList

APPLYSET_LABEL_PART_OF = "applyset.kubernetes.io/part-of"
""" Label key to use to associate objects with an ApplySet resource. """

APPLYSET_LABEL_ID = "applyset.kubernetes.io/id"
""" Label key to use on ApplySet resources to identify it. """

APPLYSET_ANNOTATION_TOOLING = "applyset.kubernetes.io/tooling"
""" Annotation key to use on ApplySet resources to specify the tooling used to apply the ApplySet. """

APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS = "applyset.kubernetes.io/contains-group-kinds"
""" Annotation key to use on ApplySet resources to specify the kinds of resources that are part of the ApplySet. """

NYL_ANNOTATION_LAST_APPLIED_CONTEXT = "nyl.io/last-applied-context"
"""
Annotation key to store contextual information about the last applied configuration.
Contains a JSON object with fields like:
- source: "cli" or "argocd"
- revision: Git commit hash (when available via ArgoCD)
- files: List of manifest file names used
"""


@dataclass
class ApplySetContext:
    """
    Contextual information about when/how the ApplySet was last applied.
    """

    source: str
    """The source of the apply operation: "cli" or "argocd"."""

    files: list[str] = field(default_factory=list)
    """List of manifest file names used to generate the resources."""

    revision: str | None = None
    """Git commit hash (when available, e.g., via ArgoCD)."""

    app_name: str | None = None
    """ArgoCD application name (when running via ArgoCD)."""

    app_namespace: str | None = None
    """ArgoCD application namespace (when running via ArgoCD)."""

    project_name: str | None = None
    """ArgoCD project name (when running via ArgoCD)."""

    source_path: str | None = None
    """ArgoCD source path (when running via ArgoCD)."""

    source_repo_url: str | None = None
    """ArgoCD source repository URL (when running via ArgoCD)."""

    target_revision: str | None = None
    """ArgoCD target revision (when running via ArgoCD)."""

    kube_version: str | None = None
    """Kubernetes version (from KUBE_VERSION env var)."""

    def to_json(self) -> str:
        """Serialize the context to a JSON string."""
        data: dict[str, Any] = {"source": self.source}
        if self.files:
            data["files"] = self.files
        if self.revision:
            data["revision"] = self.revision
        if self.app_name:
            data["app_name"] = self.app_name
        if self.app_namespace:
            data["app_namespace"] = self.app_namespace
        if self.project_name:
            data["project_name"] = self.project_name
        if self.source_path:
            data["source_path"] = self.source_path
        if self.source_repo_url:
            data["source_repo_url"] = self.source_repo_url
        if self.target_revision:
            data["target_revision"] = self.target_revision
        if self.kube_version:
            data["kube_version"] = self.kube_version
        return json.dumps(data, separators=(",", ":"))

    @staticmethod
    def from_environment(files: list[str] | None = None) -> "ApplySetContext":
        """
        Create an ApplySetContext from the current environment.

        Detects whether running via ArgoCD (by checking ARGOCD_APP_NAME env var)
        and populates the context accordingly.

        Args:
            files: List of manifest file names used to generate the resources.

        Returns:
            An ApplySetContext populated from environment variables.
        """
        argocd_app_name = os.getenv("ARGOCD_APP_NAME")
        kube_version = os.getenv("KUBE_VERSION")

        if argocd_app_name:
            # Running via ArgoCD
            return ApplySetContext(
                source="argocd",
                files=files or [],
                revision=os.getenv("ARGOCD_APP_REVISION"),
                app_name=argocd_app_name,
                app_namespace=os.getenv("ARGOCD_APP_NAMESPACE"),
                project_name=os.getenv("ARGOCD_APP_PROJECT_NAME"),
                source_path=os.getenv("ARGOCD_APP_SOURCE_PATH"),
                source_repo_url=os.getenv("ARGOCD_APP_SOURCE_REPO_URL"),
                target_revision=os.getenv("ARGOCD_APP_SOURCE_TARGET_REVISION"),
                kube_version=kube_version,
            )
        else:
            # Running via CLI
            return ApplySetContext(
                source="cli",
                files=files or [],
                kube_version=kube_version,
            )


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
    context: ApplySetContext | None = None

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

        annotations: dict[str, str] = {
            APPLYSET_ANNOTATION_TOOLING: self.tooling,
            APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS: ",".join(self.contains_group_kinds),
        }

        # Add the context annotation if available
        if self.context is not None:
            annotations[NYL_ANNOTATION_LAST_APPLIED_CONTEXT] = self.context.to_json()

        return Resource({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "annotations": annotations,
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


class ApplySetManager:
    """
    Helper class to manage applying and diffing resources associated with an ApplySet.

    This class handles:
    - Creating and configuring ApplySet resources
    - Including the ApplySet ConfigMap with other resources during apply/diff
    - Tagging resources with the applyset.kubernetes.io/part-of label
    - Looking up existing ApplySet ConfigMaps in the cluster
    - Listing all resources that are members of an ApplySet
    - Computing which resources have been removed from the manifest
    """

    def __init__(
        self,
        client: ApiClient,
        applyset: ApplySet | None = None,
        add_part_of_labels: bool = True,
    ) -> None:
        """
        Initialize the ApplySetManager.

        Args:
            client: The Kubernetes API client to use.
            applyset: The ApplySet to manage, or None to skip ApplySet-related logic.
            add_part_of_labels: Whether to add the applyset.kubernetes.io/part-of label to resources.
        """
        self.client = client
        self.applyset = applyset
        self.add_part_of_labels = add_part_of_labels

    @property
    def enabled(self) -> bool:
        """Returns True if ApplySet management is enabled (i.e., an ApplySet is configured)."""
        return self.applyset is not None

    def prepare_resources(self, resources: ResourceList) -> ResourceList:
        """
        Prepare resources for apply/diff by adding ApplySet labels and including the ApplySet ConfigMap.

        Args:
            resources: The list of resources to prepare.

        Returns:
            A new ResourceList with the ApplySet ConfigMap included (if enabled) and part-of labels added.
        """
        if not self.enabled or self.applyset is None:
            return resources

        result = ResourceList(list(resources))

        # Tag resources as part of the current apply set
        if self.add_part_of_labels:
            for resource in result:
                if "metadata" in resource:
                    labels = resource["metadata"].setdefault("labels", {})
                    if APPLYSET_LABEL_PART_OF not in labels:
                        labels[APPLYSET_LABEL_PART_OF] = self.applyset.id

        # Include the ApplySet ConfigMap with the resources
        result.insert(0, self.applyset.dump())

        return result

    def get_applyset_resource(self) -> Resource | None:
        """
        Get the ApplySet ConfigMap resource.

        Returns:
            The ApplySet ConfigMap resource, or None if ApplySet is not enabled.
        """
        if not self.enabled or self.applyset is None:
            return None
        return self.applyset.dump()

    def get_deleted_resources(self, new_resources: ResourceList) -> ResourceList:
        """
        Compute which resources have been removed from the manifest.

        This compares the new resources against the existing resources in the cluster
        that are part of this ApplySet, and returns the resources that exist in the
        cluster but are not in the new manifest.

        Args:
            new_resources: The new list of resources from the manifest.

        Returns:
            A ResourceList of resources that should be deleted (exist in cluster but not in manifest).
        """
        if not self.enabled or self.applyset is None:
            return ResourceList([])

        # Get existing resources from the cluster that belong to this ApplySet
        # Try to find the existing ApplySet ConfigMap to know which kinds to look for
        existing_applyset_cm = get_existing_applyset(
            self.applyset.name, self.applyset.namespace, self.client
        )
        kinds: list[str] = []

        if existing_applyset_cm:
            annotations = existing_applyset_cm.get("metadata", {}).get("annotations", {})
            kinds_str = annotations.get(APPLYSET_ANNOTATION_CONTAINS_GROUP_KINDS)
            if kinds_str:
                kinds = kinds_str.split(",")

        existing_resources = list_applyset_members(self.applyset.id, self.client, kinds)

        if not existing_resources:
            return ResourceList([])

        # Build a set of resource identifiers from the new manifest
        new_resource_ids = set()
        for resource in new_resources:
            resource_id = _get_resource_identifier(resource)
            if resource_id:
                new_resource_ids.add(resource_id)

        # Also add the ApplySet ConfigMap itself to avoid deleting it
        applyset_cm = self.applyset.dump()
        applyset_id = _get_resource_identifier(applyset_cm)
        if applyset_id:
            new_resource_ids.add(applyset_id)

        # Find resources that exist in the cluster but not in the new manifest
        deleted_resources: list[Resource] = []
        for resource in existing_resources:
            resource_id = _get_resource_identifier(resource)
            if resource_id and resource_id not in new_resource_ids:
                deleted_resources.append(resource)

        return ResourceList(deleted_resources)


def _get_resource_identifier(resource: Resource) -> str | None:
    """
    Get a unique identifier for a resource based on apiVersion, kind, namespace, and name.

    Args:
        resource: The resource to identify.

    Returns:
        A string identifier in the format "apiVersion/kind/namespace/name" or None if the resource
        is missing required fields.
    """
    api_version = resource.get("apiVersion")
    kind = resource.get("kind")
    metadata = resource.get("metadata", {})
    name = metadata.get("name")
    namespace = metadata.get("namespace", "")

    if not api_version or not kind or not name:
        return None

    return f"{api_version}/{kind}/{namespace}/{name}"


def get_existing_applyset(name: str, namespace: str, client: ApiClient) -> Resource | None:
    """
    Look up an existing ApplySet ConfigMap in the cluster.

    Args:
        name: The name of the ApplySet ConfigMap.
        namespace: The namespace of the ApplySet ConfigMap.
        client: The Kubernetes API client to use.

    Returns:
        The ApplySet ConfigMap resource if it exists, or None if not found.
    """
    try:
        dynamic = DynamicClient(client)
        # ConfigMap is v1
        resource_client = dynamic.resources.get(api_version="v1", kind="ConfigMap")
        resource = resource_client.get(name=name, namespace=namespace)

        # Verify it's an ApplySet ConfigMap by checking for the id label
        labels = resource.metadata.get("labels", {}).to_dict()
        if APPLYSET_LABEL_ID in labels:
            return Resource(resource.to_dict())
        return None
    except NotFoundError:
        return None


def list_applyset_members(
    applyset_id: str, client: ApiClient, kinds: list[str]
) -> ResourceList:
    """
    List all resources in the cluster that are members of an ApplySet.

    Args:
        applyset_id: The ID of the ApplySet (value of applyset.kubernetes.io/id label).
        client: The Kubernetes API client to use.
        kinds: List of resource kinds to search for.

    Returns:
        A ResourceList of all resources that have the applyset.kubernetes.io/part-of label
        matching the given ApplySet ID.
    """
    dynamic = DynamicClient(client)
    all_resources: list[Resource] = []

    resources_to_check: list[tuple[str, str]] = []

    for k in kinds:
        parts = k.split(".", 1)
        if len(parts) == 2:
            resources_to_check.append((parts[0], parts[1]))
        else:
            resources_to_check.append((parts[0], ""))

    for kind, group in resources_to_check:
        try:
            api_resources = dynamic.resources.search(kind=kind, group=group)
            if not api_resources:
                continue

            res_client = api_resources[0]

            items = res_client.get(label_selector=f"{APPLYSET_LABEL_PART_OF}={applyset_id}")
            for item in items.items:
                all_resources.append(Resource(item.to_dict()))

        except NotFoundError:
            # It's possible the resource kind doesn't exist in the cluster (e.g. CRD was removed).
            # In this case, we can just skip it.
            continue

    # Deduplicate resources by their UID
    seen_uids: set[str] = set()
    unique_resources: list[Resource] = []
    for resource in all_resources:
        uid = resource.get("metadata", {}).get("uid", "")
        if uid and uid not in seen_uids:
            seen_uids.add(uid)
            unique_resources.append(resource)

    return ResourceList(unique_resources)