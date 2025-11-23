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

    When running in ArgoCD, it authenticates using the Kubernetes service account JWT token.
    When running locally, it uses the token from `~/.vault-token` (obtained via `vault login`).

    The provider supports nested structures through dot notation, similar to the SOPS provider.
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
        """Authenticate with Vault using Kubernetes JWT token (for ArgoCD context)."""
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
            "Authenticating with Vault using Kubernetes JWT (role: {})", self.jwt_role
        )

        try:
            assert self._client is not None
            self._client.auth.kubernetes.login(role=self.jwt_role, jwt=jwt_token)
            logger.debug("Successfully authenticated with Vault using JWT")
        except Exception as exc:
            logger.error("Failed to authenticate with Vault using JWT: {}", exc)
            raise

    def _authenticate_with_token(self) -> None:
        """Authenticate with Vault using token from ~/.vault-token (for local context)."""
        token_path = Path.home() / ".vault-token"
        if not token_path.exists():
            raise RuntimeError(
                f"Vault token file not found at {token_path}. Please run 'vault login' first or set VAULT_TOKEN."
            )

        token = token_path.read_text().strip()
        assert self._client is not None
        self._client.token = token
        logger.debug("Authenticated with Vault using token from {}", token_path)

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
        Split a dotted key into the Vault secret path and the field within that secret.

        For example, "database.password" splits into ("database", "password").
        A key without dots like "api-key" returns ("api-key", None).
        """
        parts = key.split(".", 1)
        if len(parts) == 1:
            return parts[0], None
        return parts[0], parts[1]

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

        The key can use dot notation for nested access:
        - "database" retrieves the entire secret at path "database"
        - "database.password" retrieves the "password" field from the "database" secret
        - "database.credentials.username" retrieves nested fields

        Args:
            key: The key of the secret to retrieve, with optional dot notation for nested access.
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

        For dot-notation keys, this will update the specific field within the secret,
        preserving other fields. For top-level keys, this creates or replaces the entire secret.

        Args:
            key: The key of the secret to set.
            value: The value to set.
        Raises:
            KeyError: If the key is invalid.
            ValueError: If the value is invalid.
            RuntimeError: If the key cannot be set for systematic reasons.
        """
        client = self._get_client()
        secret_path, field_path = self._split_key_path(key)
        full_path = self._normalize_path(secret_path)

        if field_path is None:
            # Setting the entire secret
            if not isinstance(value, dict):
                # Wrap non-dict values in a dict for KV v2
                data = {"value": value}
            else:
                data = value
        else:
            # Setting a specific field - need to read existing data first
            try:
                existing_data = self._get_secret_data(secret_path)
            except KeyError:
                # Secret doesn't exist yet
                existing_data = {}

            # Navigate to the nested location and set the value
            parts = field_path.split(".")
            current = existing_data
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                elif not isinstance(current[part], dict):
                    raise ValueError(
                        f"Cannot set nested field '{field_path}' - parent is not a dict"
                    )
                current = current[part]

            current[parts[-1]] = value
            data = existing_data

        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=full_path, secret=data, mount_point=self.mount_point
            )
            logger.info("Set secret in Vault at path '{}'", full_path)

            # Update cache
            if self._cache is None:
                self._cache = {}
            self._cache[key] = value
        except Exception as exc:
            logger.error(
                "Failed to set secret in Vault at path '{}': {}", full_path, exc
            )
            raise RuntimeError(f"Failed to set secret: {exc}") from exc

    def unset(self, key: str, /) -> None:
        """
        Unset a secret by its key in Vault.

        For dot-notation keys, this removes the specific field from the secret.
        For top-level keys, this deletes the entire secret.

        Args:
            key: The key of the secret to unset.
        """
        client = self._get_client()
        secret_path, field_path = self._split_key_path(key)
        full_path = self._normalize_path(secret_path)

        try:
            if field_path is None:
                # Delete the entire secret
                client.secrets.kv.v2.delete_metadata_and_all_versions(
                    path=full_path, mount_point=self.mount_point
                )
                logger.info("Deleted secret from Vault at path '{}'", full_path)
            else:
                # Remove a specific field
                try:
                    existing_data = self._get_secret_data(secret_path)
                except KeyError:
                    logger.warning(
                        "Secret '{}' not found in Vault, nothing to unset", secret_path
                    )
                    return

                # Navigate to the nested location and delete the value
                parts = field_path.split(".")
                current = existing_data
                for part in parts[:-1]:
                    if part not in current or not isinstance(current[part], dict):
                        logger.warning(
                            "Field '{}' not found in secret '{}'",
                            field_path,
                            secret_path,
                        )
                        return
                    current = current[part]

                if parts[-1] in current:
                    del current[parts[-1]]
                    # Write back the modified secret
                    client.secrets.kv.v2.create_or_update_secret(
                        path=full_path,
                        secret=existing_data,
                        mount_point=self.mount_point,
                    )
                    logger.info(
                        "Removed field '{}' from secret at path '{}'",
                        field_path,
                        full_path,
                    )
                else:
                    logger.warning(
                        "Field '{}' not found in secret '{}'", field_path, secret_path
                    )

            # Update cache
            if self._cache and key in self._cache:
                del self._cache[key]

        except Exception as exc:
            logger.error(
                "Failed to unset secret in Vault at path '{}': {}", full_path, exc
            )
            raise RuntimeError(f"Failed to unset secret: {exc}") from exc
