"""
Tests for ArgoCD integration utilities.
"""

import base64
import json
import os
from unittest.mock import patch, MagicMock

from nyl.tools.argocd import (
    detect_argocd_context, 
    ArgoCDContext, 
    get_application_destination,
    get_cluster_credentials,
    ClusterInfo
)


def test_detect_argocd_context_with_all_env_vars():
    """Test ArgoCD context detection when all required environment variables are present."""
    env_vars = {
        "ARGOCD_APP_NAME": "test-app",
        "ARGOCD_APP_NAMESPACE": "argocd",
        "ARGOCD_APP_PROJECT_NAME": "default",
        "ARGOCD_APP_REVISION": "abc123",
        "ARGOCD_APP_SOURCE_PATH": "manifests",
        "ARGOCD_APP_SOURCE_REPO_URL": "https://github.com/test/repo.git"
    }
    
    with patch.dict(os.environ, env_vars, clear=False):
        context = detect_argocd_context()
        
    assert context is not None
    assert context.app_name == "test-app"
    assert context.app_namespace == "argocd"
    assert context.project_name == "default"
    assert context.revision == "abc123"
    assert context.source_path == "manifests"
    assert context.source_repo_url == "https://github.com/test/repo.git"


def test_detect_argocd_context_minimal_env_vars():
    """Test ArgoCD context detection with minimal required environment variables."""
    env_vars = {
        "ARGOCD_APP_NAME": "test-app",
        "ARGOCD_APP_NAMESPACE": "argocd", 
        "ARGOCD_APP_PROJECT_NAME": "default"
    }
    
    # Clear optional env vars
    for key in ["ARGOCD_APP_REVISION", "ARGOCD_APP_SOURCE_PATH", "ARGOCD_APP_SOURCE_REPO_URL"]:
        if key in os.environ:
            del os.environ[key]
    
    with patch.dict(os.environ, env_vars, clear=False):
        context = detect_argocd_context()
        
    assert context is not None
    assert context.app_name == "test-app"
    assert context.app_namespace == "argocd"
    assert context.project_name == "default"
    assert context.revision is None
    assert context.source_path is None
    assert context.source_repo_url is None


def test_detect_argocd_context_missing_required_env_vars():
    """Test ArgoCD context detection when required environment variables are missing."""
    # Clear all ArgoCD env vars
    argocd_env_vars = [
        "ARGOCD_APP_NAME", "ARGOCD_APP_NAMESPACE", "ARGOCD_APP_PROJECT_NAME",
        "ARGOCD_APP_REVISION", "ARGOCD_APP_SOURCE_PATH", "ARGOCD_APP_SOURCE_REPO_URL"
    ]
    
    for key in argocd_env_vars:
        if key in os.environ:
            del os.environ[key]
    
    context = detect_argocd_context()
    assert context is None


def test_detect_argocd_context_partial_required_env_vars():
    """Test ArgoCD context detection when only some required environment variables are present."""
    env_vars = {
        "ARGOCD_APP_NAME": "test-app",
        "ARGOCD_APP_NAMESPACE": "argocd"
        # Missing ARGOCD_APP_PROJECT_NAME
    }
    
    # Clear all ArgoCD env vars first
    argocd_env_vars = [
        "ARGOCD_APP_NAME", "ARGOCD_APP_NAMESPACE", "ARGOCD_APP_PROJECT_NAME",
        "ARGOCD_APP_REVISION", "ARGOCD_APP_SOURCE_PATH", "ARGOCD_APP_SOURCE_REPO_URL"
    ]
    
    for key in argocd_env_vars:
        if key in os.environ:
            del os.environ[key]
    
    with patch.dict(os.environ, env_vars, clear=False):
        context = detect_argocd_context()
        
    assert context is None


def test_get_application_destination_success():
    """Test successful retrieval of application destination."""
    # Mock the ArgoCD client and Application resource
    mock_client = MagicMock()
    mock_dynamic_client = MagicMock()
    mock_application_resource = MagicMock()
    mock_application = MagicMock()
    
    # Setup the mock chain
    with patch('nyl.tools.argocd.DynamicClient', return_value=mock_dynamic_client):
        mock_dynamic_client.resources.get.return_value = mock_application_resource
        mock_application_resource.get.return_value = mock_application
        
        # Mock application spec with destination
        mock_destination = MagicMock()
        mock_destination.name = "production-cluster"
        mock_destination.server = "https://prod-k8s.example.com"
        mock_application.spec.destination = mock_destination
        
        context = ArgoCDContext(
            app_name="test-app",
            app_namespace="argocd", 
            project_name="default"
        )
        
        result = get_application_destination(mock_client, context)
        
        assert result is not None
        assert result.name == "production-cluster"
        assert result.server == "https://prod-k8s.example.com"
        
        # Verify the correct API calls were made
        mock_dynamic_client.resources.get.assert_called_once_with(
            api_version="argoproj.io/v1alpha1",
            kind="Application"
        )
        mock_application_resource.get.assert_called_once_with(
            name="test-app",
            namespace="argocd"
        )


def test_get_application_destination_no_server():
    """Test handling of application with no destination server."""
    mock_client = MagicMock()
    mock_dynamic_client = MagicMock()
    mock_application_resource = MagicMock()
    mock_application = MagicMock()
    
    with patch('nyl.tools.argocd.DynamicClient', return_value=mock_dynamic_client):
        mock_dynamic_client.resources.get.return_value = mock_application_resource
        mock_application_resource.get.return_value = mock_application
        
        # Mock application spec with destination but no server
        mock_destination = MagicMock()
        mock_destination.name = "production-cluster"
        mock_destination.server = None
        mock_application.spec.destination = mock_destination
        
        context = ArgoCDContext(
            app_name="test-app",
            app_namespace="argocd",
            project_name="default"
        )
        
        result = get_application_destination(mock_client, context)
        assert result is None


def test_get_cluster_credentials_success():
    """Test successful retrieval of cluster credentials."""
    mock_client = MagicMock()
    mock_dynamic_client = MagicMock()
    mock_secret_resource = MagicMock()
    
    # Create mock cluster secret
    mock_secret = MagicMock()
    mock_secret.metadata.name = "cluster-prod"
    
    # Mock cluster configuration
    cluster_config = {
        "tlsClientConfig": {
            "caData": "LS0tLS1CRUdJTi==",  # base64 encoded CA cert
            "certData": "LS0tLS1CRUdJTi==",  # base64 encoded client cert
            "keyData": "LS0tLS1CRUdJTi==",   # base64 encoded client key
            "insecure": False
        },
        "bearerToken": "eyJhbGciOiJSUzI1NiIs..."
    }
    
    # Encode the secret data
    mock_secret.data = {
        "server": base64.b64encode(b"https://prod-k8s.example.com").decode('utf-8'),
        "config": base64.b64encode(json.dumps(cluster_config).encode('utf-8')).decode('utf-8')
    }
    
    # Mock secrets list response
    mock_secrets_list = MagicMock()
    mock_secrets_list.items = [mock_secret]
    
    with patch('nyl.tools.argocd.DynamicClient', return_value=mock_dynamic_client):
        mock_dynamic_client.resources.get.return_value = mock_secret_resource
        mock_secret_resource.get.return_value = mock_secrets_list
        
        cluster_info = ClusterInfo(
            name="production-cluster",
            server="https://prod-k8s.example.com",
            config={}
        )
        
        with patch.dict(os.environ, {"ARGOCD_APP_NAMESPACE": "argocd"}):
            result = get_cluster_credentials(mock_client, cluster_info)
        
        assert result is not None
        assert result["apiVersion"] == "v1"
        assert result["kind"] == "Config"
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["cluster"]["server"] == "https://prod-k8s.example.com"
        assert len(result["users"]) == 1
        assert "token" in result["users"][0]["user"]


def test_get_cluster_credentials_no_matching_server():
    """Test handling when no cluster secret matches the server URL."""
    mock_client = MagicMock()
    mock_dynamic_client = MagicMock()
    mock_secret_resource = MagicMock()
    
    # Create mock cluster secret with different server
    mock_secret = MagicMock()
    mock_secret.metadata.name = "cluster-dev"
    mock_secret.data = {
        "server": base64.b64encode(b"https://dev-k8s.example.com").decode('utf-8'),
        "config": base64.b64encode(b'{"tlsClientConfig": {}}').decode('utf-8')
    }
    
    mock_secrets_list = MagicMock()
    mock_secrets_list.items = [mock_secret]
    
    with patch('nyl.tools.argocd.DynamicClient', return_value=mock_dynamic_client):
        mock_dynamic_client.resources.get.return_value = mock_secret_resource
        mock_secret_resource.get.return_value = mock_secrets_list
        
        cluster_info = ClusterInfo(
            name="production-cluster",
            server="https://prod-k8s.example.com",  # Different from secret
            config={}
        )
        
        with patch.dict(os.environ, {"ARGOCD_APP_NAMESPACE": "argocd"}):
            result = get_cluster_credentials(mock_client, cluster_info)
        
        assert result is None