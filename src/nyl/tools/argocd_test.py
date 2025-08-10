"""
Tests for ArgoCD integration utilities.
"""

import os
from unittest.mock import patch, MagicMock

from nyl.tools.argocd import detect_argocd_context, ArgoCDContext


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