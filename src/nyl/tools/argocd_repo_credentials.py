"""
ArgoCD repository credentials support for Git operations.

This module provides functionality to query ArgoCD repository credentials from Kubernetes
and apply them to Git operations for seamless authentication.
"""
import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from kubernetes.client.api_client import ApiClient
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from loguru import logger


@dataclass
class RepoCredential:
    """Represents repository credentials from ArgoCD."""
    
    url: str
    username: str | None = None
    password: str | None = None
    ssh_private_key: str | None = None
    insecure: bool = False
    enable_lfs: bool = False
    type: str = "git"
    
    @property
    def is_ssh(self) -> bool:
        """Check if this credential uses SSH authentication."""
        return self.ssh_private_key is not None
    
    @property
    def is_https(self) -> bool:
        """Check if this credential uses HTTPS authentication."""
        return self.username is not None and self.password is not None


def query_argocd_repository_credentials(client: ApiClient, namespace: str = "argocd") -> list[RepoCredential]:
    """
    Query ArgoCD repository credentials from Kubernetes secrets.
    
    Args:
        client: Kubernetes API client
        namespace: Namespace where ArgoCD secrets are stored (default: "argocd")
        
    Returns:
        List of repository credentials found
    """
    dynamic_client = DynamicClient(client)
    
    try:
        # Get the Secret resource
        secret_resource = dynamic_client.resources.get(api_version="v1", kind="Secret")
        
        # Query secrets with ArgoCD repository labels
        secrets = secret_resource.get(namespace=namespace, label_selector="argocd.argoproj.io/secret-type in (repository,repo-creds)")
        
        credentials = []
        
        for secret in secrets.items:
            try:
                cred = _parse_secret_to_credential(secret)
                if cred:
                    credentials.append(cred)
            except Exception as e:
                logger.warning(f"Failed to parse ArgoCD secret {secret.metadata.name}: {e}")
                
        logger.debug(f"Found {len(credentials)} ArgoCD repository credentials in namespace {namespace}")
        return credentials
        
    except ApiException as e:
        if e.status == 404:
            logger.debug(f"No ArgoCD secrets found in namespace {namespace}")
            return []
        else:
            logger.warning(f"Failed to query ArgoCD repository credentials: {e}")
            return []


def _parse_secret_to_credential(secret: Any) -> RepoCredential | None:
    """Parse a Kubernetes secret into a RepoCredential."""
    data = secret.data or {}
    
    # Get URL which is required
    url = _decode_secret_data(data, "url")
    if not url:
        return None
    
    # Extract other fields
    username = _decode_secret_data(data, "username")
    password = _decode_secret_data(data, "password")
    ssh_private_key = _decode_secret_data(data, "sshPrivateKey")
    insecure = _decode_secret_data(data, "insecure") == "true"
    enable_lfs = _decode_secret_data(data, "enableLfs") == "true"
    repo_type = _decode_secret_data(data, "type") or "git"
    
    return RepoCredential(
        url=url,
        username=username,
        password=password,
        ssh_private_key=ssh_private_key,
        insecure=insecure,
        enable_lfs=enable_lfs,
        type=repo_type,
    )


def _decode_secret_data(data: dict[str, str], key: str) -> str | None:
    """Decode base64 secret data field."""
    if key not in data:
        return None
    
    try:
        return base64.b64decode(data[key]).decode("utf-8")
    except Exception:
        return None


def find_matching_credential(git_url: str, credentials: list[RepoCredential]) -> RepoCredential | None:
    """
    Find the best matching credential for a Git URL.
    
    This implements ArgoCD's credential matching logic:
    1. Exact URL match (from 'repository' secrets)
    2. Prefix URL match (from 'repo-creds' credential templates)
    
    Args:
        git_url: The Git repository URL to find credentials for
        credentials: List of available repository credentials
        
    Returns:
        The best matching credential, or None if no match found
    """
    if not credentials:
        return None
    
    # Normalize the input URL for comparison
    normalized_url = _normalize_git_url(git_url)
    
    # First pass: look for exact matches
    for cred in credentials:
        if _normalize_git_url(cred.url) == normalized_url:
            logger.debug(f"Found exact credential match for {git_url}")
            return cred
    
    # Second pass: look for prefix matches (credential templates)
    best_match = None
    best_match_length = 0
    
    for cred in credentials:
        cred_url_normalized = _normalize_git_url(cred.url)
        if normalized_url.startswith(cred_url_normalized):
            if len(cred_url_normalized) > best_match_length:
                best_match = cred
                best_match_length = len(cred_url_normalized)
    
    if best_match:
        logger.debug(f"Found prefix credential match for {git_url}")
    
    return best_match


def _normalize_git_url(url: str) -> str:
    """
    Normalize a Git URL for comparison.
    
    This removes trailing slashes and ensures consistent format for matching.
    """
    # Handle SSH URLs (git@host:path format)
    if "@" in url and "://" not in url:
        return url.rstrip("/")
    
    # Handle HTTPS/HTTP URLs
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        # Reconstruct without query/fragment and normalize path
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    
    # For other formats, just remove trailing slash
    return url.rstrip("/")


def apply_credential_to_git_url(git_url: str, credential: RepoCredential) -> str:
    """
    Apply repository credential to a Git URL for authentication.
    
    For HTTPS URLs with username/password, embeds the credentials in the URL.
    For SSH URLs, returns the original URL (SSH key setup is handled separately).
    
    Args:
        git_url: Original Git repository URL
        credential: Repository credential to apply
        
    Returns:
        Git URL with authentication applied (for HTTPS) or original URL (for SSH)
    """
    if credential.is_https:
        # For HTTPS authentication, embed credentials in URL
        parsed = urlparse(git_url)
        if parsed.scheme in ("http", "https"):
            # Construct URL with embedded credentials
            netloc = f"{credential.username}:{credential.password}@{parsed.netloc}"
            return f"{parsed.scheme}://{netloc}{parsed.path}"
    
    # For SSH or if no HTTPS credentials, return original URL
    return git_url