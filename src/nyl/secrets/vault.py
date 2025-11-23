import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import hvac  # type: ignore[import-untyped]
from databind.core import Union
from loguru import logger

from nyl.secrets import SecretProvider, SecretValue
from nyl.tools.di import DependenciesProvider


@Union.register(SecretProvider, name="vault")
@dataclass
class VaultSecretProvider(SecretProvider):
    """
    This secrets provider retrieves secrets from HashiCorp Vault using the KV secrets engine.

    Authentication methods:
    - JWT (ArgoCD): Supports both Kubernetes service account tokens and Nyl-issued
      ArgoCD-application-specific workload identity tokens
    - Token (local): Uses token from VAULT_TOKEN env var or ~/.vault-token file

    Key format: Use # to separate secret path from field access with dot notation:
    - "database" -> entire secret at path "database"
    - "database#password" -> "password" field from "database" secret
    - "db/prod#credentials.username" -> nested field from "db/prod" secret

    This allows secrets with dots in their path names to be accessed correctly.
    """

    url: str
    """
    The URL of the Vault server (e.g., "https://vault.example.com:8200").
    """

    mount_point: str = "secret"
    """
    The mount point of the KV secrets engine in Vault. Defaults to "secret".
    """

    path: str = ""
    """
    The path prefix within the KV secrets engine where secrets are stored.
    For example, if path is "myapp/", secrets will be retrieved from "secret/data/myapp/...".
    """

    jwt_role: str | None = None
    """
    The Vault role to use for JWT authentication when running in ArgoCD.
    If not specified, JWT authentication will not be attempted.
    """

    jwt_auth_method: str = "kubernetes"
    """
    The JWT authentication method to use. Options:
    - "kubernetes": Use Kubernetes service account token (simple, single-tenant)
    - "nyl": Use Nyl-issued ArgoCD application-specific token (multi-tenant)
    Defaults to "kubernetes".
    """

    namespace: str | None = None
    """
    The Vault namespace to use (Vault Enterprise feature).
    """

    _client: hvac.Client | None = field(init=False, repr=False, default=None)
    _cache: dict[str, SecretValue] | None = field(init=False, repr=False, default=None)

    def _get_client(self) -> hvac.Client:
        """Get or create a Vault client with appropriate authentication."""
        if self._client is not None:
            return self._client

        self._client = hvac.Client(url=self.url, namespace=self.namespace)

        # Try to authenticate
        if self._is_argocd_context() and self.jwt_role:
            self._authenticate_with_jwt()
        else:
            self._authenticate_with_token()

        if not self._client.is_authenticated():
            raise RuntimeError("Failed to authenticate with Vault")

        logger.info("Successfully authenticated with Vault at {}", self.url)
        return self._client

    def _is_argocd_context(self) -> bool:
        """Check if we're running in an ArgoCD context by looking for ArgoCD environment variables."""
        return "ARGOCD_APP_NAME" in os.environ

    def _authenticate_with_jwt(self) -> None:
        """
        Authenticate with Vault using JWT token (for ArgoCD context).

        Supports two authentication methods:
        1. Kubernetes service account token (simple, single-tenant)
        2. Nyl-issued ArgoCD application-specific token (multi-tenant)
        """
        if self.jwt_auth_method == "nyl":
            self._authenticate_with_nyl_jwt()
        else:
            self._authenticate_with_kubernetes_jwt()

    def _authenticate_with_kubernetes_jwt(self) -> None:
        """Authenticate with Vault using Kubernetes service account JWT token."""
        jwt_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
        if not jwt_path.exists():
            logger.warning(
                "JWT authentication requested but token file not found at {}. Falling back to token auth.",
                jwt_path,
            )
            self._authenticate_with_token()
            return

        jwt_token = jwt_path.read_text().strip()
        logger.info(
            "Authenticating with Vault using Kubernetes JWT (role: {})",
            self.jwt_role,
        )

        try:
            assert self._client is not None
            self._client.auth.kubernetes.login(role=self.jwt_role, jwt=jwt_token)
            logger.debug("Successfully authenticated with Vault using Kubernetes JWT")
        except Exception as exc:
            logger.error(
                "Failed to authenticate with Vault using Kubernetes JWT: {}", exc
            )
            raise

    def _authenticate_with_nyl_jwt(self) -> None:
        """
        Authenticate with Vault using Nyl-issued ArgoCD application-specific JWT token.

        This token is issued by Nyl and contains claims about the ArgoCD application
        being deployed, enabling multi-tenant secure access to Vault secrets.

        The token payload includes:
        - iss: Issuer (e.g., "https://my-argocd.example.com/#nyl-v1")
        - aud: Audience (Vault URL)
        - sub: Subject (e.g., "project:default:application:my-argo-app")
        - argocd_project: ArgoCD project name
        - argocd_app: ArgoCD application name
        - repository: Git repository URL
        """
        # Check for Nyl-issued JWT token in environment variable
        jwt_token = os.environ.get("NYL_VAULT_JWT")
        if not jwt_token:
            logger.error(
                "Nyl JWT authentication requested but NYL_VAULT_JWT environment variable not set. "
                "This token should be issued by Nyl based on the ArgoCD application context."
            )
            raise RuntimeError(
                "NYL_VAULT_JWT environment variable not set for Nyl JWT authentication"
            )

        logger.info(
            "Authenticating with Vault using Nyl-issued JWT (role: {})", self.jwt_role
        )

        try:
            assert self._client is not None
            # Use JWT auth method (not kubernetes auth)
            self._client.auth.jwt.login(role=self.jwt_role, jwt=jwt_token)
            logger.debug("Successfully authenticated with Vault using Nyl-issued JWT")
        except Exception as exc:
            logger.error(
                "Failed to authenticate with Vault using Nyl-issued JWT: {}", exc
            )
            raise

    def _authenticate_with_token(self) -> None:
        """Authenticate with Vault using token from ~/.vault-token or VAULT_TOKEN env var (for local context)."""
        # First check VAULT_TOKEN environment variable
        token = os.environ.get("VAULT_TOKEN")
        if token:
            logger.debug("Using Vault token from VAULT_TOKEN environment variable")
        else:
            # Fall back to token file
            token_path = Path.home() / ".vault-token"
            if not token_path.exists():
                raise RuntimeError(
                    f"Vault token file not found at {token_path}. Please run 'vault login' first or set VAULT_TOKEN environment variable."
                )
            token = token_path.read_text().strip()
            logger.debug("Authenticated with Vault using token from {}", token_path)

        assert self._client is not None
        self._client.token = token

    def _normalize_path(self, key: str) -> str:
        """Normalize a secret key to a full Vault path."""
        # Combine the path prefix with the key
        if self.path:
            full_path = f"{self.path.rstrip('/')}/{key}"
        else:
            full_path = key

        return full_path

    def _split_key_path(self, key: str) -> tuple[str, str | None]:
        """
        Split a key into the Vault secret path and the field within that secret.

        The key format is: "path/to/secret#field.nested.path"
        - Everything before the hash (#) is the secret path in Vault
        - Everything after the hash is the field path using dot notation for nested access

        For example:
        - "database#password" -> ("database", "password")
        - "path/to/secret#credentials.username" -> ("path/to/secret", "credentials.username")
        - "api-key" -> ("api-key", None) - returns entire secret
        """
        if "#" in key:
            parts = key.split("#", 1)
            return parts[0], parts[1]
        return key, None

    def _get_secret_data(self, secret_path: str) -> dict[str, Any]:
        """Retrieve the data from a Vault secret at the given path."""
        client = self._get_client()
        full_path = self._normalize_path(secret_path)

        try:
            # For KV v2, we need to read from the /data/ path
            response = client.secrets.kv.v2.read_secret_version(
                path=full_path,
                mount_point=self.mount_point,
                raise_on_deleted_version=True,
            )
            return response["data"]["data"]
        except hvac.exceptions.InvalidPath:
            raise KeyError(f"Secret not found at path: {full_path}")
        except Exception as exc:
            logger.error(
                "Failed to read secret from Vault at path '{}': {}", full_path, exc
            )
            raise

    def _get_nested_value(self, data: dict[str, Any], field_path: str) -> SecretValue:
        """Get a nested value from a dictionary using dot notation."""
        parts = field_path.split(".")
        value = data
        for part in parts:
            if not isinstance(value, dict):
                raise KeyError(f"Cannot access field '{part}' in non-dict value")
            if part not in value:
                raise KeyError(f"Field '{part}' not found")
            value = value[part]
        return value

    def load(self, force: bool = False) -> dict[str, SecretValue]:
        """Load all secrets from Vault (not implemented - use individual get calls)."""
        # Note: For Vault, it's not efficient to load all secrets at once
        # as they may be spread across multiple paths. We'll populate the cache on-demand.
        if self._cache is None or force:
            self._cache = {}
        return self._cache

    # SecretProvider

    def init(self, config_file: Path, dependencies: DependenciesProvider) -> None:
        """Initialize the Vault provider."""
        # No path resolution needed for Vault URLs
        pass

    def keys(self) -> Iterable[str]:
        """
        Return an iterator over all keys in the provider.

        Note: This is not efficiently implementable for Vault without listing all secrets,
        which may not be feasible in a multi-tenant environment. Returns cached keys only.
        """
        if self._cache:
            return self._cache.keys()
        return []

    def get(self, key: str, /) -> SecretValue:
        """
        Retrieve a secret by key from Vault.

        The key format is "path/to/secret#field.path" where:
        - Everything before # is the Vault secret path
        - Everything after # is the field path using dot notation for nested access

        Examples:
        - "database" retrieves the entire secret at path "database"
        - "database#password" retrieves the "password" field from the "database" secret
        - "db/prod#credentials.username" retrieves nested field from "db/prod" secret

        Args:
            key: The key of the secret to retrieve. Use # to separate path from field access.
        Returns:
            The secret value.
        Raises:
            KeyError: If the key does not exist.
        """
        # Check cache first
        if self._cache and key in self._cache:
            return self._cache[key]

        # Split the key into secret path and field path
        secret_path, field_path = self._split_key_path(key)

        # Get the secret data from Vault
        data = self._get_secret_data(secret_path)

        result: SecretValue
        if field_path is None:
            # Return the entire secret
            result = data
        else:
            # Navigate to the nested field
            result = self._get_nested_value(data, field_path)

        # Cache the result
        if self._cache is None:
            self._cache = {}
        self._cache[key] = result

        return result

    def set(self, key: str, value: SecretValue, /) -> None:
        """
        Set the value of a key in Vault.

        This operation is not supported for the Vault provider. Vault secrets should be
        managed through Vault's own interface or CLI tools.

        Raises:
            NotImplementedError: Always raised as this operation is not supported.
        """
        raise NotImplementedError(
            "Setting secrets is not supported for the Vault provider. "
            "Please manage Vault secrets through Vault's interface or CLI."
        )

    def unset(self, key: str, /) -> None:
        """
        Unset a secret by its key in Vault.

        This operation is not supported for the Vault provider. Vault secrets should be
        managed through Vault's own interface or CLI tools.

        Raises:
            NotImplementedError: Always raised as this operation is not supported.
        """
        raise NotImplementedError(
            "Unsetting secrets is not supported for the Vault provider. "
            "Please manage Vault secrets through Vault's interface or CLI."
        )
