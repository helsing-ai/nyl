"""Tests for ArgoCD repository credentials functionality."""
import base64
from unittest.mock import Mock, patch

import pytest

from nyl.tools.argocd_repo_credentials import (
    RepoCredential,
    apply_credential_to_git_url,
    find_matching_credential,
    query_argocd_repository_credentials,
    _normalize_git_url,
    _parse_secret_to_credential,
)


def test_repo_credential_properties():
    """Test RepoCredential property methods."""
    # SSH credential
    ssh_cred = RepoCredential(
        url="git@github.com:myorg/repo.git",
        ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\n..."
    )
    assert ssh_cred.is_ssh
    assert not ssh_cred.is_https
    
    # HTTPS credential
    https_cred = RepoCredential(
        url="https://github.com/myorg/repo.git",
        username="user",
        password="token"
    )
    assert not https_cred.is_ssh
    assert https_cred.is_https
    
    # No credentials
    no_cred = RepoCredential(url="https://github.com/myorg/repo.git")
    assert not no_cred.is_ssh
    assert not no_cred.is_https


def test_normalize_git_url():
    """Test Git URL normalization."""
    # HTTPS URLs
    assert _normalize_git_url("https://github.com/myorg/repo.git") == "https://github.com/myorg/repo.git"
    assert _normalize_git_url("https://github.com/myorg/repo.git/") == "https://github.com/myorg/repo.git"
    assert _normalize_git_url("https://github.com/myorg/") == "https://github.com/myorg"
    
    # SSH URLs
    assert _normalize_git_url("git@github.com:myorg/repo.git") == "git@github.com:myorg/repo.git"
    assert _normalize_git_url("git@github.com:myorg/repo.git/") == "git@github.com:myorg/repo.git"
    
    # Other formats
    assert _normalize_git_url("file:///path/to/repo/") == "file:///path/to/repo"


def test_find_matching_credential():
    """Test credential matching logic."""
    credentials = [
        # Exact match for specific repo
        RepoCredential(
            url="https://github.com/myorg/specific-repo.git",
            username="user1",
            password="pass1"
        ),
        # Prefix match for all repos in org
        RepoCredential(
            url="https://github.com/myorg/",
            username="user2", 
            password="pass2"
        ),
        # Broader prefix match for all GitHub
        RepoCredential(
            url="https://github.com/",
            username="user3",
            password="pass3"
        ),
    ]
    
    # Test exact match takes precedence
    match = find_matching_credential("https://github.com/myorg/specific-repo.git", credentials)
    assert match is not None
    assert match.username == "user1"
    
    # Test prefix match for other repo in same org
    match = find_matching_credential("https://github.com/myorg/other-repo.git", credentials)
    assert match is not None
    assert match.username == "user2"
    
    # Test broader prefix match
    match = find_matching_credential("https://github.com/otherorg/repo.git", credentials)
    assert match is not None
    assert match.username == "user3"
    
    # Test no match
    match = find_matching_credential("https://gitlab.com/myorg/repo.git", credentials)
    assert match is None
    
    # Test with trailing slashes
    match = find_matching_credential("https://github.com/myorg/specific-repo.git/", credentials)
    assert match is not None
    assert match.username == "user1"


def test_apply_credential_to_git_url():
    """Test applying credentials to Git URLs."""
    # HTTPS credential
    https_cred = RepoCredential(
        url="https://github.com/myorg/",
        username="user",
        password="token123"
    )
    
    result = apply_credential_to_git_url("https://github.com/myorg/repo.git", https_cred)
    assert result == "https://user:token123@github.com/myorg/repo.git"
    
    # SSH credential (should return original URL)
    ssh_cred = RepoCredential(
        url="git@github.com:myorg/",
        ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\n..."
    )
    
    result = apply_credential_to_git_url("git@github.com:myorg/repo.git", ssh_cred)
    assert result == "git@github.com:myorg/repo.git"
    
    # No credentials (should return original URL)
    no_cred = RepoCredential(url="https://github.com/myorg/")
    result = apply_credential_to_git_url("https://github.com/myorg/repo.git", no_cred)
    assert result == "https://github.com/myorg/repo.git"


def test_parse_secret_to_credential():
    """Test parsing Kubernetes secret to RepoCredential."""
    # Mock secret with HTTPS credentials
    secret_data = {
        "url": base64.b64encode(b"https://github.com/myorg/repo.git").decode(),
        "username": base64.b64encode(b"user").decode(), 
        "password": base64.b64encode(b"token").decode(),
        "type": base64.b64encode(b"git").decode(),
    }
    
    mock_secret = Mock()
    mock_secret.data = secret_data
    
    cred = _parse_secret_to_credential(mock_secret)
    assert cred is not None
    assert cred.url == "https://github.com/myorg/repo.git"
    assert cred.username == "user"
    assert cred.password == "token"
    assert cred.type == "git"
    assert cred.is_https
    assert not cred.is_ssh
    
    # Mock secret with SSH credentials
    secret_data_ssh = {
        "url": base64.b64encode(b"git@github.com:myorg/repo.git").decode(),
        "sshPrivateKey": base64.b64encode(b"-----BEGIN RSA PRIVATE KEY-----\nkey_content\n-----END RSA PRIVATE KEY-----").decode(),
    }
    
    mock_secret_ssh = Mock()
    mock_secret_ssh.data = secret_data_ssh
    
    cred_ssh = _parse_secret_to_credential(mock_secret_ssh)
    assert cred_ssh is not None
    assert cred_ssh.url == "git@github.com:myorg/repo.git"
    assert cred_ssh.ssh_private_key == "-----BEGIN RSA PRIVATE KEY-----\nkey_content\n-----END RSA PRIVATE KEY-----"
    assert cred_ssh.is_ssh
    assert not cred_ssh.is_https
    
    # Mock secret without URL (should return None)
    mock_secret_no_url = Mock()
    mock_secret_no_url.data = {"username": base64.b64encode(b"user").decode()}
    
    cred_no_url = _parse_secret_to_credential(mock_secret_no_url)
    assert cred_no_url is None


def test_query_argocd_repository_credentials():
    """Test querying ArgoCD repository credentials from Kubernetes."""
    # Mock Kubernetes client and dynamic client
    mock_client = Mock()
    mock_dynamic_client = Mock()
    mock_secret_resource = Mock()
    
    # Mock secret data
    mock_secrets = Mock()
    mock_secrets.items = [
        Mock(
            metadata=Mock(name="github-creds"),
            data={
                "url": base64.b64encode(b"https://github.com/myorg/").decode(),
                "username": base64.b64encode(b"user").decode(),
                "password": base64.b64encode(b"token").decode(),
            }
        )
    ]
    
    mock_secret_resource.get.return_value = mock_secrets
    mock_dynamic_client.resources.get.return_value = mock_secret_resource
    
    # Mock the DynamicClient constructor
    with patch('nyl.tools.argocd_repo_credentials.DynamicClient', return_value=mock_dynamic_client):
        credentials = query_argocd_repository_credentials(mock_client)
    
    # Verify the correct API calls were made
    mock_dynamic_client.resources.get.assert_called_once_with(api_version="v1", kind="Secret")
    mock_secret_resource.get.assert_called_once_with(
        namespace="argocd", 
        label_selector="argocd.argoproj.io/secret-type in (repository,repo-creds)"
    )
    
    # Verify credentials were parsed correctly
    assert len(credentials) == 1
    assert credentials[0].url == "https://github.com/myorg/"
    assert credentials[0].username == "user"
    assert credentials[0].password == "token"