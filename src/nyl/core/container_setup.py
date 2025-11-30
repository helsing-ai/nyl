"""Container setup utilities for dependency injection.

This module provides functions to configure DIContainer instances with
all the dependencies needed by Nyl commands.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from kubernetes.client.api_client import ApiClient
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config
from loguru import logger

from nyl.core.di import DIContainer
from nyl.profiles import DEFAULT_PROFILE, ProfileManager
from nyl.project.config import ProjectConfig
from nyl.secrets.config import SecretsConfig

if TYPE_CHECKING:
    from nyl.tools.kubectl import Kubectl


def setup_base_container(
    container: DIContainer,
    *,
    in_cluster: bool = False,
    profile: str | None = None,
    working_dir: Path | None = None,
) -> None:
    """Register base dependencies in the container.

    This sets up the foundational dependencies that all commands need:
    - ProfileManager
    - ProjectConfig
    - SecretsConfig
    - ApiClient

    Args:
        container: The container to register dependencies in
        in_cluster: Whether to use in-cluster Kubernetes configuration
        profile: Optional profile name to use
        working_dir: Working directory for the command
    """
    if working_dir is None:
        working_dir = Path.cwd()

    # Register ProfileManager
    container.register_factory(ProfileManager, lambda: ProfileManager.load(required=False))

    # Register ProjectConfig
    def _load_project_config() -> ProjectConfig:
        # ProjectConfig.load expects a DependenciesProvider, but we're migrating away from that
        # For now, create a temporary adapter
        from nyl.tools.di import DependenciesProvider

        temp_provider = DependenciesProvider.default()
        temp_provider.set(ProfileManager, container.resolve(ProfileManager))
        return ProjectConfig.load(dependencies=temp_provider)

    container.register_factory(ProjectConfig, _load_project_config)

    # Register SecretsConfig
    def _load_secrets_config() -> SecretsConfig:
        from nyl.tools.di import DependenciesProvider

        temp_provider = DependenciesProvider.default()
        temp_provider.set(ProfileManager, container.resolve(ProfileManager))
        temp_provider.set(ProjectConfig, container.resolve(ProjectConfig))
        return SecretsConfig.load(dependencies=temp_provider)

    container.register_factory(SecretsConfig, _load_secrets_config)

    # Register ApiClient
    def _create_api_client() -> ApiClient:
        if in_cluster:
            logger.info("Using in-cluster configuration.")
            load_incluster_config()
            return ApiClient()

        profile_manager = container.resolve(ProfileManager)
        # If no profile to activate is specified, and there are no profiles defined, we're not activating a
        # a profile. It should be valid to use Nyl without a `nyl-profiles.yaml` file.
        if profile is not None or profile_manager.config.profiles:
            active_profile = profile or DEFAULT_PROFILE
            with profile_manager:
                active = profile_manager.activate_profile(active_profile)
                load_kube_config(str(active.kubeconfig))
        else:
            logger.opt(colors=True).info(
                "No <yellow>nyl-profiles.yaml</> file found, using default kubeconfig and context."
            )
            load_kube_config()
        return ApiClient()

    container.register_factory(ApiClient, _create_api_client)


def setup_service_container(
    container: DIContainer,
    *,
    kubectl: "Kubectl | None" = None,
) -> None:
    """Register service dependencies in the container.

    This sets up the service layer that commands use:
    - ManifestLoaderService
    - NamespaceResolverService
    - KubernetesApplyService

    Args:
        container: The container to register dependencies in
        kubectl: Optional Kubectl instance (will be created if not provided)
    """
    # Import services here to avoid circular imports
    from nyl.services.kubernetes_apply import KubernetesApplyService
    from nyl.services.manifest import ManifestLoaderService
    from nyl.services.namespace import NamespaceResolverService
    from nyl.tools.kubectl import Kubectl

    # Register ManifestLoaderService (stateless, can share instance)
    container.register_singleton(ManifestLoaderService, ManifestLoaderService())

    # Register NamespaceResolverService (stateless, can share instance)
    container.register_singleton(NamespaceResolverService, NamespaceResolverService())

    # Register Kubectl if provided
    if kubectl is not None:
        container.register_singleton(Kubectl, kubectl)

    # Register KubernetesApplyService
    def _create_k8s_apply() -> KubernetesApplyService:
        kubectl_instance = container.resolve(Kubectl)
        # We'll need kube_version from somewhere - for now we'll make it optional
        from nyl.generator.dispatch import DispatchingGenerator

        # Check if we have a generator registered
        if container.has(DispatchingGenerator):
            kube_version = container.resolve(DispatchingGenerator).kube_version
        else:
            import os

            kube_version = os.getenv("KUBE_VERSION", "v1.28.0")

        return KubernetesApplyService(kubectl=kubectl_instance, kube_version=kube_version)

    container.register_factory(KubernetesApplyService, _create_k8s_apply)
