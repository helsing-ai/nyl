"""Service for applying Kubernetes resources and managing ApplySets."""

from loguru import logger

from nyl.models.errors import ApplySetError
from nyl.resources.applyset import ApplySet
from nyl.services.manifest import ManifestsWithSource
from nyl.tools import yaml
from nyl.tools.kubectl import Kubectl
from nyl.tools.types import ResourceList


class KubernetesApplyService:
    """Service for applying resources to Kubernetes clusters.

    This service centralizes all Kubernetes operations including:
    - ApplySet lifecycle management (find, create, validate, tag)
    - Kubectl apply operations
    - Kubectl diff operations
    - YAML output for dry-run mode
    """

    def __init__(self, kubectl: Kubectl, kube_version: str):
        """Create a KubernetesApplyService.

        Args:
            kubectl: Kubectl wrapper for executing commands
            kube_version: Kubernetes version for ApplySet compatibility
        """
        self.kubectl = kubectl
        self.kube_version = kube_version

    def find_or_create_applyset(
        self,
        source: ManifestsWithSource,
        namespace: str,
        auto_generate: bool,
    ) -> ApplySet | None:
        """Find or create an ApplySet for the manifest.

        Strategy:
        1. Look for existing ApplySet resource in manifest
        2. If found, validate only one exists and remove from resources
        3. If not found and auto_generate=True, create new one
        4. Return None if no ApplySet and auto_generate=False

        Args:
            source: Manifest source to search and modify
            namespace: Default namespace for auto-generated ApplySet
            auto_generate: Whether to auto-generate if not found

        Returns:
            ApplySet if found/created, None otherwise

        Raises:
            ApplySetError: If multiple ApplySets found or namespace required but missing
        """
        applyset: ApplySet | None = None
        applyset_count = 0

        # Search for ApplySet resources
        for resource in list(source.resources):
            if ApplySet.matches(resource):
                applyset_count += 1
                if applyset is not None:
                    raise ApplySetError(
                        f"Multiple ApplySet resources found in {source.file}",
                        file_path=str(source.file),
                        applyset_count=applyset_count,
                    )
                applyset = ApplySet.load(resource)
                source.resources.remove(resource)

        # Auto-generate if needed
        if not applyset and auto_generate:
            if not namespace:
                raise ApplySetError(
                    f"No default namespace defined for {source.file}, but it is required for the "
                    "automatically generated nyl.io/v1/ApplySet resource",
                    file_path=str(source.file),
                    hint="Specify --namespace or add a Namespace resource to your manifest",
                )

            applyset_name = namespace
            applyset = ApplySet.new(applyset_name)
            logger.info(f"Automatically creating ApplySet for {source.file} (name: {applyset_name})")

        return applyset

    def prepare_applyset(
        self,
        applyset: ApplySet,
        resources: ResourceList,
    ) -> None:
        """Prepare an ApplySet for application.

        This:
        1. Sets the group kinds based on resources
        2. Sets the tooling label for kubectl compatibility
        3. Validates the ApplySet

        Args:
            applyset: The ApplySet to prepare
            resources: Resources that will be applied with this ApplySet
        """
        applyset.set_group_kinds(resources)

        # HACK: Kubectl 1.30 can't create the custom resource without tooling label
        # See: https://github.com/helsing-ai/nyl/issues/5
        applyset.tooling = f"kubectl/v{self.kube_version}"

        applyset.validate()

    def apply_with_applyset(
        self,
        resources: ResourceList,
        applyset: ApplySet | None,
        source_file: str,
        prune: bool = False,
    ) -> None:
        """Apply resources to the cluster with optional ApplySet.

        Args:
            resources: Resources to apply
            applyset: Optional ApplySet to use
            source_file: Source file name for logging
            prune: Whether to prune resources not in manifest
        """
        if applyset:
            # First, apply the ApplySet parent object
            logger.info(f"Kubectl-apply ApplySet resource {applyset.reference} from {source_file}")
            self.kubectl.apply(
                ResourceList([applyset.dump()]),
                force_conflicts=True,
            )

            # Then apply the resources with the ApplySet
            if resources:
                self.kubectl.apply(
                    resources,
                    applyset=applyset.reference,
                    prune=prune,
                )
        else:
            # Apply without ApplySet
            if resources:
                self.kubectl.apply(resources)

    def diff_with_applyset(
        self,
        resources: ResourceList,
        applyset: ApplySet | None,
    ) -> None:
        """Show diff of resources against cluster.

        Args:
            resources: Resources to diff
            applyset: Optional ApplySet to diff
        """
        if applyset:
            # Diff the ApplySet
            self.kubectl.diff(ResourceList([applyset.dump()]))

        # Diff the resources
        if resources:
            if applyset:
                self.kubectl.diff(resources, applyset=applyset.reference)
            else:
                self.kubectl.diff(resources)

    def output_yaml(
        self,
        resources: ResourceList,
        applyset: ApplySet | None,
    ) -> None:
        """Output resources as YAML (dry-run mode).

        Args:
            resources: Resources to output
            applyset: Optional ApplySet to output
        """
        if applyset:
            print("---")
            print(yaml.dumps(applyset.dump()))

        for resource in resources:
            print("---")
            print(yaml.dumps(resource))

    def tag_resources_with_applyset(
        self,
        resources: ResourceList,
        applyset: ApplySet,
        applyset_part_of: bool = False,
    ) -> None:
        """Tag resources with ApplySet labels.

        Args:
            resources: Resources to tag
            applyset: ApplySet to associate with
            applyset_part_of: Whether to add part-of label
        """
        if applyset_part_of:
            from nyl.resources.applyset import APPLYSET_LABEL_PART_OF

            for resource in resources:
                if "metadata" not in resource:
                    resource["metadata"] = {}
                if "labels" not in resource["metadata"]:
                    resource["metadata"]["labels"] = {}

                resource["metadata"]["labels"][APPLYSET_LABEL_PART_OF] = applyset.reference

    def find_namespace_resources(self, resources: ResourceList) -> set[str]:
        """Find all namespace names defined in resources.

        Args:
            resources: Resources to search

        Returns:
            Set of namespace names
        """
        namespaces: set[str] = set()
        for resource in resources:
            if resource.get("apiVersion") == "v1" and resource.get("kind") == "Namespace":
                namespaces.add(resource["metadata"]["name"])
        return namespaces
