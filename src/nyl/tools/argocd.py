"""
ArgoCD integration utilities for Nyl.

This module provides utilities for detecting ArgoCD environment and resolving
destination cluster credentials for external cluster support.
"""

import base64
import json
import os
from dataclasses import dataclass
from typing import Optional

from kubernetes.client.api_client import ApiClient
from kubernetes.config import new_client_from_config_dict
from kubernetes.dynamic.client import DynamicClient
from kubernetes.client.exceptions import ApiException
from loguru import logger


@dataclass
class ArgoCDContext:
    """
    ArgoCD context information extracted from environment variables.
    """
    app_name: str
    app_namespace: str
    project_name: str
    revision: Optional[str] = None
    source_path: Optional[str] = None
    source_repo_url: Optional[str] = None


@dataclass
class ClusterInfo:
    """
    Information about a destination cluster from ArgoCD.
    """
    name: Optional[str]
    server: str
    config: dict


def detect_argocd_context() -> Optional[ArgoCDContext]:
    """
    Detect if running in ArgoCD environment by checking for ArgoCD environment variables.
    
    Returns:
        ArgoCDContext if running in ArgoCD, None otherwise.
    """
    app_name = os.getenv("ARGOCD_APP_NAME")
    app_namespace = os.getenv("ARGOCD_APP_NAMESPACE") 
    project_name = os.getenv("ARGOCD_APP_PROJECT_NAME")
    
    if not all([app_name, app_namespace, project_name]):
        return None
        
    return ArgoCDContext(
        app_name=app_name,
        app_namespace=app_namespace,
        project_name=project_name,
        revision=os.getenv("ARGOCD_APP_REVISION"),
        source_path=os.getenv("ARGOCD_APP_SOURCE_PATH"),
        source_repo_url=os.getenv("ARGOCD_APP_SOURCE_REPO_URL")
    )


def get_application_destination(argocd_client: ApiClient, context: ArgoCDContext) -> Optional[ClusterInfo]:
    """
    Fetch the ArgoCD Application resource and extract destination cluster information.
    
    Args:
        argocd_client: Kubernetes API client for the ArgoCD cluster
        context: ArgoCD context information
        
    Returns:
        ClusterInfo for the destination cluster, or None if not found
    """
    try:
        dynamic_client = DynamicClient(argocd_client)
        
        # Get the Application resource
        application_resource = dynamic_client.resources.get(
            api_version="argoproj.io/v1alpha1", 
            kind="Application"
        )
        
        application = application_resource.get(
            name=context.app_name,
            namespace=context.app_namespace
        )
        
        destination = application.spec.destination
        cluster_name = getattr(destination, 'name', None)
        cluster_server = getattr(destination, 'server', None)
        
        if not cluster_server:
            logger.warning("Application {} has no destination server configured", context.app_name)
            return None
            
        logger.debug("Found destination cluster: name={}, server={}", cluster_name, cluster_server)
        
        return ClusterInfo(
            name=cluster_name,
            server=cluster_server,
            config={}  # Will be populated by get_cluster_credentials
        )
        
    except ApiException as e:
        logger.warning("Failed to fetch Application {}/{}: {}", context.app_namespace, context.app_name, e)
        return None
    except Exception as e:
        logger.warning("Error getting application destination: {}", e)
        return None


def get_cluster_credentials(argocd_client: ApiClient, cluster_info: ClusterInfo) -> Optional[dict]:
    """
    Fetch cluster credentials from ArgoCD cluster secrets.
    
    Args:
        argocd_client: Kubernetes API client for the ArgoCD cluster
        cluster_info: Information about the destination cluster
        
    Returns:
        Kubernetes config dict for the destination cluster, or None if not found
    """
    try:
        dynamic_client = DynamicClient(argocd_client)
        
        # Get secrets with ArgoCD cluster label
        secret_resource = dynamic_client.resources.get(api_version="v1", kind="Secret")
        
        # List all secrets in the ArgoCD namespace with cluster label
        secrets = secret_resource.get(
            namespace=os.getenv("ARGOCD_APP_NAMESPACE", "argocd"),
            label_selector="argocd.argoproj.io/secret-type=cluster"
        )
        
        for secret in secrets.items:
            if not hasattr(secret, 'data') or not secret.data:
                continue
                
            # Decode the cluster server URL from the secret
            try:
                server_data = secret.data.get('server')
                if not server_data:
                    continue
                    
                server_url = base64.b64decode(server_data).decode('utf-8')
                
                # Match against our target cluster
                if server_url == cluster_info.server:
                    logger.debug("Found cluster credentials secret: {}", secret.metadata.name)
                    
                    # Decode cluster configuration
                    config_data = secret.data.get('config')
                    if not config_data:
                        logger.warning("Cluster secret {} has no config data", secret.metadata.name)
                        continue
                        
                    config_json = base64.b64decode(config_data).decode('utf-8')
                    config = json.loads(config_json)
                    
                    # Build kubernetes config dict
                    kube_config = {
                        'apiVersion': 'v1',
                        'kind': 'Config',
                        'clusters': [{
                            'name': cluster_info.name or 'argocd-cluster',
                            'cluster': {
                                'server': cluster_info.server,
                                'certificate-authority-data': config.get('tlsClientConfig', {}).get('caData'),
                                'insecure-skip-tls-verify': config.get('tlsClientConfig', {}).get('insecure', False)
                            }
                        }],
                        'users': [{
                            'name': 'argocd-user',
                            'user': {}
                        }],
                        'contexts': [{
                            'name': 'argocd-context',
                            'context': {
                                'cluster': cluster_info.name or 'argocd-cluster',
                                'user': 'argocd-user'
                            }
                        }],
                        'current-context': 'argocd-context'
                    }
                    
                    # Add authentication data
                    user_config = kube_config['users'][0]['user']
                    tls_config = config.get('tlsClientConfig', {})
                    
                    if 'certData' in tls_config and 'keyData' in tls_config:
                        user_config['client-certificate-data'] = tls_config['certData']
                        user_config['client-key-data'] = tls_config['keyData']
                    
                    if 'bearerToken' in config:
                        user_config['token'] = config['bearerToken']
                        
                    # Handle AWS IAM authenticator
                    if 'execProviderConfig' in config:
                        exec_config = config['execProviderConfig']
                        user_config['exec'] = {
                            'apiVersion': exec_config.get('apiVersion', 'client.authentication.k8s.io/v1beta1'),
                            'command': exec_config.get('command'),
                            'args': exec_config.get('args', []),
                            'env': exec_config.get('env', [])
                        }
                    
                    return kube_config
                    
            except (ValueError, KeyError, TypeError) as e:
                logger.debug("Failed to decode cluster secret {}: {}", secret.metadata.name, e)
                continue
        
        logger.warning("No cluster credentials found for server: {}", cluster_info.server)
        return None
        
    except ApiException as e:
        logger.warning("Failed to list cluster secrets: {}", e)
        return None
    except Exception as e:
        logger.warning("Error getting cluster credentials: {}", e)
        return None


def create_destination_client(argocd_client: ApiClient, context: ArgoCDContext) -> Optional[ApiClient]:
    """
    Create a Kubernetes API client for the destination cluster.
    
    Args:
        argocd_client: Kubernetes API client for the ArgoCD cluster  
        context: ArgoCD context information
        
    Returns:
        ApiClient for the destination cluster, or None if unable to create
    """
    try:
        # Get destination cluster info from Application
        cluster_info = get_application_destination(argocd_client, context)
        if not cluster_info:
            return None
            
        # Special case: if destination is the same as ArgoCD cluster, return the ArgoCD client
        if cluster_info.server in ['https://kubernetes.default.svc', 'https://kubernetes.default.svc.cluster.local']:
            logger.debug("Destination cluster is the same as ArgoCD cluster, using ArgoCD client")
            return argocd_client
        
        # Get credentials for destination cluster
        kube_config = get_cluster_credentials(argocd_client, cluster_info)
        if not kube_config:
            return None
            
        # Create API client from config
        client = new_client_from_config_dict(kube_config)
        logger.info("Successfully created destination cluster client for: {}", cluster_info.server)
        return client
        
    except Exception as e:
        logger.warning("Failed to create destination cluster client: {}", e)
        return None