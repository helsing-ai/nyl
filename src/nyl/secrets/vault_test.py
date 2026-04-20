import os
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

import hvac
import pytest

from nyl.secrets.vault import VaultSecretProvider
from nyl.tools.di import DependenciesProvider


@pytest.fixture
def mock_vault_client():
    """Create a mock Vault client for testing."""
    with unittest.mock.patch("hvac.Client") as mock_client_class:
        mock_client = unittest.mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_authenticated.return_value = True
        yield mock_client


@pytest.fixture
def provider_with_mock(mock_vault_client):
    """Create a VaultSecretProvider with mocked client."""
    provider = VaultSecretProvider(
        url="https://vault.example.com:8200", mount_point="secret", path="myapp/"
    )
    provider._client = mock_vault_client
    return provider


def test_VaultSecretProvider_init() -> None:
    """Test basic initialization of VaultSecretProvider."""
    provider = VaultSecretProvider(
        url="https://vault.example.com:8200",
        mount_point="secret",
        path="myapp/",
        jwt_role="my-role",
    )
    provider.init(
        config_file=Path("/tmp/nyl-secrets.yaml"),
        dependencies=DependenciesProvider.default(),
    )

    assert provider.url == "https://vault.example.com:8200"
    assert provider.mount_point == "secret"
    assert provider.path == "myapp/"
    assert provider.jwt_role == "my-role"


def test_VaultSecretProvider_is_argocd_context() -> None:
    """Test detection of ArgoCD context."""
    provider = VaultSecretProvider(url="https://vault.example.com:8200")

    # Without ArgoCD env vars
    assert not provider._is_argocd_context()

    # With ArgoCD env vars
    with unittest.mock.patch.dict(os.environ, {"ARGOCD_APP_NAME": "test-app"}):
        assert provider._is_argocd_context()


def test_VaultSecretProvider_normalize_path() -> None:
    """Test path normalization."""
    provider = VaultSecretProvider(url="https://vault.example.com:8200", path="myapp/")
    assert provider._normalize_path("database") == "myapp/database"

    provider_no_prefix = VaultSecretProvider(
        url="https://vault.example.com:8200", path=""
    )
    assert provider_no_prefix._normalize_path("database") == "database"


def test_VaultSecretProvider_split_key_path() -> None:
    """Test splitting of keys using hash separator."""
    provider = VaultSecretProvider(url="https://vault.example.com:8200")

    # Test without hash - entire secret
    assert provider._split_key_path("database") == ("database", None)

    # Test with hash - field access
    assert provider._split_key_path("database#password") == ("database", "password")

    # Test with nested field path
    assert provider._split_key_path("database#credentials.username") == (
        "database",
        "credentials.username",
    )

    # Test with dots in path (now supported!)
    assert provider._split_key_path("db.prod#password") == ("db.prod", "password")
    assert provider._split_key_path("path/to/secret.v2#field") == (
        "path/to/secret.v2",
        "field",
    )


def test_VaultSecretProvider_get_simple(provider_with_mock, mock_vault_client) -> None:
    """Test getting a simple secret value."""
    # Mock the Vault response for a simple secret
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"username": "admin", "password": "secret123"}}
    }

    result = provider_with_mock.get("database")
    assert result == {"username": "admin", "password": "secret123"}

    # Verify the call was made with correct parameters
    mock_vault_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="myapp/database", mount_point="secret", raise_on_deleted_version=True
    )


def test_VaultSecretProvider_get_nested(provider_with_mock, mock_vault_client) -> None:
    """Test getting a nested secret value using hash separator and dot notation."""
    # Mock the Vault response
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"username": "admin", "password": "secret123"}}
    }

    result = provider_with_mock.get("database#password")
    assert result == "secret123"


def test_VaultSecretProvider_get_deeply_nested(
    provider_with_mock, mock_vault_client
) -> None:
    """Test getting a deeply nested secret value."""
    # Mock the Vault response with nested structure
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {
            "data": {
                "credentials": {
                    "primary": {"username": "admin", "password": "secret123"}
                }
            }
        }
    }

    result = provider_with_mock.get("database#credentials.primary.username")
    assert result == "admin"


def test_VaultSecretProvider_get_not_found(
    provider_with_mock, mock_vault_client
) -> None:
    """Test handling of non-existent secrets."""
    mock_vault_client.secrets.kv.v2.read_secret_version.side_effect = (
        hvac.exceptions.InvalidPath()
    )

    with pytest.raises(KeyError, match="Secret not found at path"):
        provider_with_mock.get("nonexistent")


def test_VaultSecretProvider_get_cache(provider_with_mock, mock_vault_client) -> None:
    """Test that secrets are cached after first retrieval."""
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"username": "admin", "password": "secret123"}}
    }

    # First call
    result1 = provider_with_mock.get("database")
    assert result1 == {"username": "admin", "password": "secret123"}

    # Second call should use cache
    result2 = provider_with_mock.get("database")
    assert result2 == {"username": "admin", "password": "secret123"}

    # Vault should only be called once
    assert mock_vault_client.secrets.kv.v2.read_secret_version.call_count == 1


def test_VaultSecretProvider_set_not_implemented(
    provider_with_mock, mock_vault_client
) -> None:
    """Test that setting secrets raises NotImplementedError."""
    with pytest.raises(
        NotImplementedError,
        match="Setting secrets is not supported for the Vault provider",
    ):
        provider_with_mock.set(
            "database", {"username": "admin", "password": "secret123"}
        )


def test_VaultSecretProvider_unset_not_implemented(
    provider_with_mock, mock_vault_client
) -> None:
    """Test that unsetting secrets raises NotImplementedError."""
    with pytest.raises(
        NotImplementedError,
        match="Unsetting secrets is not supported for the Vault provider",
    ):
        provider_with_mock.unset("database")


def test_VaultSecretProvider_keys_empty() -> None:
    """Test keys method with empty cache."""
    provider = VaultSecretProvider(url="https://vault.example.com:8200")
    assert list(provider.keys()) == []


def test_VaultSecretProvider_keys_with_cache(
    provider_with_mock, mock_vault_client
) -> None:
    """Test keys method returns cached keys."""
    # Add some items to cache
    provider_with_mock._cache = {
        "database": {"user": "admin"},
        "database#password": "secret",
    }

    keys = list(provider_with_mock.keys())
    assert set(keys) == {"database", "database#password"}


def test_VaultSecretProvider_authenticate_with_token() -> None:
    """Test authentication with token file."""
    with TemporaryDirectory() as tmpdir:
        token_path = Path(tmpdir) / ".vault-token"
        token_path.write_text("test-token-123\n")

        with unittest.mock.patch("hvac.Client") as mock_client_class:
            mock_client = unittest.mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.is_authenticated.return_value = True

            provider = VaultSecretProvider(url="https://vault.example.com:8200")
            provider._client = mock_client  # Set the client before calling authenticate

            with unittest.mock.patch("pathlib.Path.home", return_value=Path(tmpdir)):
                provider._authenticate_with_token()

            assert mock_client.token == "test-token-123"


def test_VaultSecretProvider_authenticate_with_env_token() -> None:
    """Test authentication with VAULT_TOKEN environment variable."""
    with unittest.mock.patch("hvac.Client") as mock_client_class:
        mock_client = unittest.mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_authenticated.return_value = True

        provider = VaultSecretProvider(url="https://vault.example.com:8200")
        provider._client = mock_client

        with unittest.mock.patch.dict(os.environ, {"VAULT_TOKEN": "env-token-456"}):
            provider._authenticate_with_token()

        assert mock_client.token == "env-token-456"


def test_VaultSecretProvider_authenticate_with_kubernetes_jwt() -> None:
    """Test authentication with Kubernetes service account JWT token (ArgoCD context)."""
    with unittest.mock.patch("hvac.Client") as mock_client_class:
        mock_client = unittest.mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_authenticated.return_value = True

        provider = VaultSecretProvider(
            url="https://vault.example.com:8200",
            jwt_role="my-role",
            jwt_auth_method="kubernetes",
        )
        provider._client = mock_client

        # Mock the JWT token path directly in the module
        with unittest.mock.patch("nyl.secrets.vault.Path") as mock_path_class:
            mock_jwt_path = unittest.mock.MagicMock()
            mock_jwt_path.exists.return_value = True
            mock_jwt_path.read_text.return_value = "test-jwt-token\n"
            mock_path_class.return_value = mock_jwt_path

            provider._authenticate_with_kubernetes_jwt()

        mock_client.auth.kubernetes.login.assert_called_once_with(
            role="my-role", jwt="test-jwt-token"
        )


def test_VaultSecretProvider_authenticate_with_nyl_jwt() -> None:
    """Test authentication with Nyl-issued ArgoCD application-specific JWT token."""
    with unittest.mock.patch("hvac.Client") as mock_client_class:
        mock_client = unittest.mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_authenticated.return_value = True

        provider = VaultSecretProvider(
            url="https://vault.example.com:8200",
            jwt_role="my-role",
            jwt_auth_method="nyl",
        )
        provider._client = mock_client

        # Set the Nyl JWT token (as would be done by the template command)
        provider.set_nyl_jwt_token("nyl-issued-jwt-token")

        provider._authenticate_with_nyl_jwt()

        mock_client.auth.jwt.login.assert_called_once_with(
            role="my-role", jwt="nyl-issued-jwt-token"
        )


def test_VaultSecretProvider_authenticate_with_nyl_jwt_missing_token() -> None:
    """Test that Nyl JWT authentication fails when NYL_VAULT_JWT is not set."""
    with unittest.mock.patch("hvac.Client") as mock_client_class:
        mock_client = unittest.mock.MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_authenticated.return_value = True

        provider = VaultSecretProvider(
            url="https://vault.example.com:8200",
            jwt_role="my-role",
            jwt_auth_method="nyl",
        )
        provider._client = mock_client

        with pytest.raises(RuntimeError, match="token not set"):
            provider._authenticate_with_nyl_jwt()
            provider._authenticate_with_nyl_jwt()
