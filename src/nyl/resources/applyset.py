import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

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
    """

    def __init__(self, applyset: ApplySet | None = None, add_part_of_labels: bool = True) -> None:
        """
        Initialize the ApplySetManager.

        Args:
            applyset: The ApplySet to manage, or None to skip ApplySet-related logic.
            add_part_of_labels: Whether to add the applyset.kubernetes.io/part-of label to resources.
        """
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
