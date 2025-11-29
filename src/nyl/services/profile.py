"""Service for profile resolution and Kubernetes client management."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from kubernetes.client.api_client import ApiClient
from loguru import logger

from nyl.models.errors import ProfileNotFoundError
from nyl.profiles import ActivatedProfile, ProfileManager
from nyl.tools import yaml


class ProfileService:
    """Service for resolving profiles and managing Kubernetes API clients.

    This service consolidates profile resolution logic that was previously
    duplicated between run.py and template.py. It handles:
    - Resolving Nyl profiles from ProfileManager
    - Falling back to kubeconfig contexts when profile not found
    - Creating API clients from profiles
    """

    def __init__(self, profile_manager: ProfileManager | None):
        """Create a ProfileService.

        Args:
            profile_manager: Optional ProfileManager for Nyl profiles.
                           If None, only kubeconfig fallback is available.
        """
        self.profile_manager = profile_manager

    def resolve_profile(
        self,
        profile_name: str | None,
        inherit_kubeconfig: bool = False,
        required: bool = True,
    ) -> ActivatedProfile | None:
        """Resolve a profile by name.

        Resolution strategy:
        1. Try to find a Nyl profile with the given name
        2. If not found and inherit_kubeconfig=True, look for kubeconfig context
        3. If required=True and nothing found, raise error

        Args:
            profile_name: Name of the profile/context to resolve
            inherit_kubeconfig: Whether to fall back to kubeconfig contexts
            required: Whether to raise error if profile not found

        Returns:
            ActivatedProfile if found, None if not found and not required

        Raises:
            ProfileNotFoundError: If profile not found and required=True
        """
        if profile_name is None:
            if required:
                raise ProfileNotFoundError(
                    "default",
                    available_profiles=self._get_available_profile_names(),
                    hint="Specify a profile with --profile or define a 'default' profile",
                )
            return None

        # Try Nyl profile first
        if self.profile_manager and profile_name in self.profile_manager.config.profiles:
            with self.profile_manager:
                activated = self.profile_manager.activate_profile(profile_name)
            logger.debug(f"Activated Nyl profile: {profile_name}")
            return activated

        # Try kubeconfig context if allowed
        if inherit_kubeconfig:
            return self._resolve_from_kubeconfig(profile_name)

        # Profile not found and no fallback allowed
        if required:
            available = self._get_available_profile_names()
            raise ProfileNotFoundError(
                profile_name,
                available_profiles=available,
                hint="Use --inherit-kubeconfig to fall back to kubeconfig contexts, "
                "or add the profile to nyl-profiles.yaml",
            )

        return None

    def _resolve_from_kubeconfig(self, context_name: str) -> ActivatedProfile:
        """Resolve a context from the kubeconfig file.

        Args:
            context_name: Name of the kubeconfig context

        Returns:
            ActivatedProfile with trimmed kubeconfig

        Raises:
            ProfileNotFoundError: If context not found in kubeconfig
        """
        kubeconfig_path = Path(os.environ.get("KUBECONFIG", "~/.kube/config")).expanduser()

        if not kubeconfig_path.is_file():
            raise ProfileNotFoundError(
                context_name,
                hint=f"Kubeconfig file not found at {kubeconfig_path}",
            )

        try:
            kubeconfig_data = yaml.loads(kubeconfig_path.read_text())
            kubeconfig_data = self._trim_to_context(kubeconfig_data, context_name)
        except ValueError as e:
            raise ProfileNotFoundError(
                context_name,
                hint=f"Context '{context_name}' not found in kubeconfig",
            ) from e

        logger.info(f"Using kubeconfig context '{context_name}' from {kubeconfig_path}")

        # Write the trimmed kubeconfig to a temporary file
        tmpdir = TemporaryDirectory()
        # Note: caller should manage cleanup
        temp_kubeconfig = Path(tmpdir.name) / "kubeconfig"
        temp_kubeconfig.write_text(yaml.dumps(kubeconfig_data))
        temp_kubeconfig.chmod(0o600)

        return ActivatedProfile(kubeconfig=temp_kubeconfig)

    def _trim_to_context(self, kubeconfig_data: dict, context_name: str) -> dict:
        """Trim kubeconfig to only include the specified context.

        Args:
            kubeconfig_data: Full kubeconfig data
            context_name: Context to keep

        Returns:
            Trimmed kubeconfig data

        Raises:
            ValueError: If context not found
        """
        # Find the context
        contexts = kubeconfig_data.get("contexts", [])
        context = next((c for c in contexts if c.get("name") == context_name), None)
        if not context:
            raise ValueError(f"Context '{context_name}' not found")

        # Get cluster and user names from context
        cluster_name = context["context"]["cluster"]
        user_name = context["context"]["user"]

        # Find cluster and user
        clusters = kubeconfig_data.get("clusters", [])
        users = kubeconfig_data.get("users", [])

        cluster = next((c for c in clusters if c.get("name") == cluster_name), None)
        user = next((u for u in users if u.get("name") == user_name), None)

        if not cluster or not user:
            raise ValueError(f"Invalid context '{context_name}'")

        # Return trimmed kubeconfig
        return {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": context_name,
            "contexts": [context],
            "clusters": [cluster],
            "users": [user],
        }

    def _get_available_profile_names(self) -> list[str]:
        """Get list of available profile names.

        Returns:
            List of profile names from ProfileManager, or empty list if no manager
        """
        if self.profile_manager:
            return list(self.profile_manager.config.profiles.keys())
        return []

    def get_api_client(self, profile: ActivatedProfile) -> ApiClient:
        """Create a Kubernetes API client from an activated profile.

        Args:
            profile: The activated profile with kubeconfig

        Returns:
            Configured ApiClient
        """
        # Set environment variable for kubernetes client
        os.environ["KUBECONFIG"] = str(profile.kubeconfig.absolute())

        # Load kube config and create client
        from kubernetes.config.kube_config import load_kube_config

        load_kube_config()
        return ApiClient()
