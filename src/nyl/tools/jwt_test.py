import os
import time
import unittest.mock

import jwt as pyjwt
import pytest

from nyl.tools.jwt import (
    NylJwtClaims,
    generate_nyl_jwt,
    generate_nyl_jwt_from_argocd_env,
)


def test_NylJwtClaims_to_payload() -> None:
    """Test converting claims to JWT payload."""
    claims = NylJwtClaims(
        issuer="https://argocd.example.com/#nyl-v1",
        audience="https://vault.example.com:8200",
        argocd_project="default",
        argocd_app="my-app",
        repository="git@github.com:example/repo.git",
    )

    payload = claims.to_payload()

    assert payload["iss"] == "https://argocd.example.com/#nyl-v1"
    assert payload["aud"] == "https://vault.example.com:8200"
    assert payload["sub"] == "project:default:application:my-app"
    assert payload["argocd_project"] == "default"
    assert payload["argocd_app"] == "my-app"
    assert payload["repository"] == "git@github.com:example/repo.git"
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]


def test_NylJwtClaims_to_payload_without_repository() -> None:
    """Test JWT payload without repository."""
    claims = NylJwtClaims(
        issuer="https://argocd.example.com/#nyl-v1",
        audience="https://vault.example.com:8200",
        argocd_project="default",
        argocd_app="my-app",
        repository=None,
    )

    payload = claims.to_payload()

    assert "repository" not in payload


def test_generate_nyl_jwt() -> None:
    """Test generating a Nyl JWT with explicit parameters."""
    token = generate_nyl_jwt(
        argocd_project="test-project",
        argocd_app="test-app",
        vault_url="https://vault.example.com:8200",
        signing_key="test-secret-key",
        repository="git@github.com:test/repo.git",
        issuer="https://argocd.example.com/#nyl-v1",
    )

    # Decode the token to verify its contents
    decoded = pyjwt.decode(
        token,
        "test-secret-key",
        algorithms=["HS256"],
        audience="https://vault.example.com:8200",
    )

    assert decoded["iss"] == "https://argocd.example.com/#nyl-v1"
    assert decoded["aud"] == "https://vault.example.com:8200"
    assert decoded["sub"] == "project:test-project:application:test-app"
    assert decoded["argocd_project"] == "test-project"
    assert decoded["argocd_app"] == "test-app"
    assert decoded["repository"] == "git@github.com:test/repo.git"


def test_generate_nyl_jwt_default_issuer() -> None:
    """Test generating a Nyl JWT with default issuer."""
    token = generate_nyl_jwt(
        argocd_project="test-project",
        argocd_app="test-app",
        vault_url="https://vault.example.com:8200",
        signing_key="test-secret-key",
    )

    decoded = pyjwt.decode(
        token,
        "test-secret-key",
        algorithms=["HS256"],
        audience="https://vault.example.com:8200",
    )

    assert decoded["iss"] == "https://argocd/#nyl-v1"


def test_generate_nyl_jwt_from_argocd_env() -> None:
    """Test generating a Nyl JWT from ArgoCD environment variables."""
    with unittest.mock.patch.dict(
        os.environ,
        {
            "ARGOCD_APP_NAME": "my-app",
            "ARGOCD_APP_PROJECT_NAME": "my-project",
            "ARGOCD_APP_SOURCE_REPO_URL": "git@github.com:example/repo.git",
            "ARGOCD_SERVER": "argocd.example.com",
        },
    ):
        token = generate_nyl_jwt_from_argocd_env(
            vault_url="https://vault.example.com:8200", signing_key="test-secret-key"
        )

        decoded = pyjwt.decode(
            token,
            "test-secret-key",
            algorithms=["HS256"],
            audience="https://vault.example.com:8200",
        )

        assert decoded["iss"] == "https://argocd.example.com/#nyl-v1"
        assert decoded["aud"] == "https://vault.example.com:8200"
        assert decoded["sub"] == "project:my-project:application:my-app"
        assert decoded["argocd_project"] == "my-project"
        assert decoded["argocd_app"] == "my-app"
        assert decoded["repository"] == "git@github.com:example/repo.git"


def test_generate_nyl_jwt_from_argocd_env_default_project() -> None:
    """Test generating a Nyl JWT with default project when not specified."""
    with unittest.mock.patch.dict(
        os.environ,
        {
            "ARGOCD_APP_NAME": "my-app",
            # No ARGOCD_APP_PROJECT_NAME set
            "ARGOCD_APP_SOURCE_REPO_URL": "git@github.com:example/repo.git",
        },
        clear=False,
    ):
        token = generate_nyl_jwt_from_argocd_env(
            vault_url="https://vault.example.com:8200", signing_key="test-secret-key"
        )

        decoded = pyjwt.decode(
            token,
            "test-secret-key",
            algorithms=["HS256"],
            audience="https://vault.example.com:8200",
        )

        assert decoded["argocd_project"] == "default"


def test_generate_nyl_jwt_from_argocd_env_missing_app_name() -> None:
    """Test that generating JWT fails when ARGOCD_APP_NAME is not set."""
    with unittest.mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            RuntimeError, match="ARGOCD_APP_NAME environment variable not set"
        ):
            generate_nyl_jwt_from_argocd_env(
                vault_url="https://vault.example.com:8200",
                signing_key="test-secret-key",
            )


def test_jwt_token_expiration() -> None:
    """Test that JWT token has appropriate expiration."""
    token = generate_nyl_jwt(
        argocd_project="test-project",
        argocd_app="test-app",
        vault_url="https://vault.example.com:8200",
        signing_key="test-secret-key",
    )

    decoded = pyjwt.decode(
        token,
        "test-secret-key",
        algorithms=["HS256"],
        audience="https://vault.example.com:8200",
    )

    # Token should expire approximately 1 hour from now
    expected_exp = time.time() + 3600
    assert abs(decoded["exp"] - expected_exp) < 5  # Allow 5 seconds tolerance
