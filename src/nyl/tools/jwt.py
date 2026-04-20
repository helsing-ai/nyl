"""
JWT token generation for Nyl-issued workload identity tokens.

This module provides functionality to generate JWT tokens that assert the identity
of an ArgoCD application being templated by Nyl, for use with Vault authentication
in multi-tenant environments.
"""

import os
import time
from dataclasses import dataclass
from typing import Any

import jwt
from loguru import logger


@dataclass
class NylJwtClaims:
    """Claims for a Nyl-issued JWT token asserting ArgoCD application identity."""

    issuer: str
    """The issuer of the token (e.g., "https://my-argocd.example.com/#nyl-v1")."""

    audience: str
    """The audience for the token (e.g., Vault URL)."""

    argocd_project: str
    """The ArgoCD project name."""

    argocd_app: str
    """The ArgoCD application name."""

    repository: str | None
    """The Git repository URL (if available)."""

    def to_payload(self) -> dict[str, Any]:
        """Convert claims to JWT payload."""
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": f"project:{self.argocd_project}:application:{self.argocd_app}",
            "argocd_project": self.argocd_project,
            "argocd_app": self.argocd_app,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,  # Token valid for 1 hour
        }
        if self.repository:
            payload["repository"] = self.repository
        return payload


def generate_nyl_jwt_from_argocd_env(vault_url: str, signing_key: str) -> str:
    """
    Generate a Nyl-issued JWT token based on ArgoCD environment variables.

    This function reads ArgoCD environment variables to extract the application
    identity and generates a JWT token that can be used to authenticate with Vault.

    Args:
        vault_url: The Vault server URL (used as the audience claim).
        signing_key: The private key to sign the JWT with (HS256 algorithm).

    Returns:
        A signed JWT token as a string.

    Raises:
        RuntimeError: If required ArgoCD environment variables are not set.
    """
    # Extract ArgoCD environment variables
    argocd_app_name = os.getenv("ARGOCD_APP_NAME")
    argocd_project = os.getenv("ARGOCD_APP_PROJECT_NAME") or "default"
    argocd_repo = os.getenv("ARGOCD_APP_SOURCE_REPO_URL")

    if not argocd_app_name:
        raise RuntimeError(
            "Cannot generate Nyl JWT token: ARGOCD_APP_NAME environment variable not set. "
            "This token can only be generated when running in ArgoCD context."
        )

    # Determine the issuer (ArgoCD server URL with nyl-v1 fragment)
    # In ArgoCD context, we might not have the server URL directly, so we construct it
    # or use a configured value
    argocd_server = os.getenv("ARGOCD_SERVER") or os.getenv(
        "ARGOCD_APPLICATION_NAME", "argocd"
    )
    issuer = f"https://{argocd_server}/#nyl-v1"

    claims = NylJwtClaims(
        issuer=issuer,
        audience=vault_url,
        argocd_project=argocd_project,
        argocd_app=argocd_app_name,
        repository=argocd_repo,
    )

    logger.debug(
        "Generating Nyl JWT token for ArgoCD app '{}' in project '{}'",
        argocd_app_name,
        argocd_project,
    )

    # Generate the JWT token using HS256 algorithm
    token = jwt.encode(claims.to_payload(), signing_key, algorithm="HS256")

    return token


def generate_nyl_jwt(
    argocd_project: str,
    argocd_app: str,
    vault_url: str,
    signing_key: str,
    repository: str | None = None,
    issuer: str | None = None,
) -> str:
    """
    Generate a Nyl-issued JWT token with explicit parameters.

    This is useful for testing or when ArgoCD environment variables are not available.

    Args:
        argocd_project: The ArgoCD project name.
        argocd_app: The ArgoCD application name.
        vault_url: The Vault server URL (used as the audience claim).
        signing_key: The private key to sign the JWT with (HS256 algorithm).
        repository: Optional Git repository URL.
        issuer: Optional custom issuer. If not provided, uses a default.

    Returns:
        A signed JWT token as a string.
    """
    if not issuer:
        issuer = "https://argocd/#nyl-v1"

    claims = NylJwtClaims(
        issuer=issuer,
        audience=vault_url,
        argocd_project=argocd_project,
        argocd_app=argocd_app,
        repository=repository,
    )

    token = jwt.encode(claims.to_payload(), signing_key, algorithm="HS256")
    return token
