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
    """Test splitting of dotted keys."""
    provider = VaultSecretProvider(url="https://vault.example.com:8200")

    assert provider._split_key_path("database") == ("database", None)
    assert provider._split_key_path("database.password") == ("database", "password")
    assert provider._split_key_path("database.credentials.username") == (
        "database",
        "credentials.username",
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
    """Test getting a nested secret value using dot notation."""
    # Mock the Vault response
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"username": "admin", "password": "secret123"}}
    }

    result = provider_with_mock.get("database.password")
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

    result = provider_with_mock.get("database.credentials.primary.username")
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


def test_VaultSecretProvider_set_entire_secret(
    provider_with_mock, mock_vault_client
) -> None:
    """Test setting an entire secret."""
    provider_with_mock.set("database", {"username": "admin", "password": "secret123"})

    mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
        path="myapp/database",
        secret={"username": "admin", "password": "secret123"},
        mount_point="secret",
    )


def test_VaultSecretProvider_set_entire_secret_non_dict_raises(
    provider_with_mock, mock_vault_client
) -> None:
    """Test that setting a top-level secret with a non-dict value raises an error."""
    with pytest.raises(
        ValueError,
        match="Top-level secrets in Vault must be dictionaries",
    ):
        provider_with_mock.set("api-key", "secret123")


def test_VaultSecretProvider_set_nested_field(
    provider_with_mock, mock_vault_client
) -> None:
    """Test setting a nested field in an existing secret."""
    # Mock existing secret
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"username": "admin", "password": "old_password"}}
    }

    provider_with_mock.set("database.password", "new_password")

    # Should have read the existing secret first
    mock_vault_client.secrets.kv.v2.read_secret_version.assert_called_once()

    # Should have written back with updated value
    mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
        path="myapp/database",
        secret={"username": "admin", "password": "new_password"},
        mount_point="secret",
    )


def test_VaultSecretProvider_set_nested_field_new_secret(
    provider_with_mock, mock_vault_client
) -> None:
    """Test setting a nested field when the secret doesn't exist yet."""
    # Mock that secret doesn't exist
    mock_vault_client.secrets.kv.v2.read_secret_version.side_effect = (
        hvac.exceptions.InvalidPath()
    )

    provider_with_mock.set("database.password", "secret123")

    # Should have written a new secret
    mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
        path="myapp/database", secret={"password": "secret123"}, mount_point="secret"
    )


def test_VaultSecretProvider_unset_entire_secret(
    provider_with_mock, mock_vault_client
) -> None:
    """Test deleting an entire secret."""
    provider_with_mock.unset("database")

    mock_vault_client.secrets.kv.v2.delete_metadata_and_all_versions.assert_called_once_with(
        path="myapp/database", mount_point="secret"
    )


def test_VaultSecretProvider_unset_nested_field(
    provider_with_mock, mock_vault_client
) -> None:
    """Test removing a nested field from a secret."""
    # Mock existing secret
    mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {
            "data": {"username": "admin", "password": "secret123", "api_key": "key123"}
        }
    }

    provider_with_mock.unset("database.password")

    # Should have read the existing secret
    mock_vault_client.secrets.kv.v2.read_secret_version.assert_called_once()

    # Should have written back without the password field
    mock_vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
        path="myapp/database",
        secret={"username": "admin", "api_key": "key123"},
        mount_point="secret",
    )


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
        "database.password": "secret",
    }

    keys = list(provider_with_mock.keys())
    assert set(keys) == {"database", "database.password"}


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


def test_VaultSecretProvider_authenticate_with_jwt() -> None:
    """Test authentication with JWT token (ArgoCD context)."""
    with TemporaryDirectory() as tmpdir:
        jwt_path = Path(tmpdir) / "token"
        jwt_path.write_text("test-jwt-token\n")

        with unittest.mock.patch("hvac.Client") as mock_client_class:
            mock_client = unittest.mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.is_authenticated.return_value = True

            provider = VaultSecretProvider(
                url="https://vault.example.com:8200", jwt_role="my-role"
            )
            provider._client = mock_client

            with (
                unittest.mock.patch("pathlib.Path.exists", return_value=True),
                unittest.mock.patch(
                    "pathlib.Path.read_text", return_value="test-jwt-token\n"
                ),
            ):
                provider._authenticate_with_jwt()

            mock_client.auth.kubernetes.login.assert_called_once_with(
                role="my-role", jwt="test-jwt-token"
            )
