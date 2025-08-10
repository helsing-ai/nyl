# Cluster connectivity

Nyl may need to reach out to the Kubernetes API for various reasons, some of which are fundamental and others are
optional.

When using Nyl as an ArgoCD plugin, to enable the plugin to reach out to the Kubernetes API, you must configure the
`argocd-repo-server` service account with the necessary permissions. See [ArgoCD Plugin](./argocd-plugin.md) for more
information.

## External destination cluster support

**New in v0.10.6**: Nyl now supports external destination clusters when used as an ArgoCD plugin. This means that
`lookup()` calls will automatically work against the destination cluster specified in your ArgoCD Application, even
when it's different from the cluster where ArgoCD itself is running.

### How it works

When Nyl detects that it's running in an ArgoCD environment (via ArgoCD environment variables), it will:

1. **Fetch the Application resource** from the local ArgoCD cluster to determine the destination cluster
2. **Lookup cluster credentials** from ArgoCD's cluster secrets
3. **Create a destination cluster API client** using the found credentials
4. **Use the destination client** for all `lookup()` calls

This process is completely transparent and requires no additional configuration. Your existing ArgoCD Applications will
automatically gain external cluster lookup support.

### Backwards compatibility

- **Non-ArgoCD usage**: Continues to work unchanged using your kubeconfig or Nyl profiles
- **Same-cluster deployments**: ArgoCD Applications deploying to the same cluster as ArgoCD continue to work as before
- **External cluster deployments**: Now work automatically with lookup support
- **Fallback behavior**: If destination cluster credentials cannot be found, Nyl falls back to using the ArgoCD cluster

### Requirements

For external cluster lookup support to work:

1. The ArgoCD Application must specify a destination cluster
2. The destination cluster must be registered in ArgoCD with appropriate credentials
3. The `argocd-repo-server` must have permissions to read Applications and cluster secrets in the ArgoCD namespace

Example ArgoCD Application with external destination:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/gitops.git
    path: manifests
    plugin:
      name: nyl-v1
  destination:
    # External cluster - lookups will work against this cluster
    server: https://external-k8s.example.com
    namespace: production
```

## Kubernetes API versions

When Nyl invokes `helm template`, it must pass along a full list of all available API versions in the cluster to
allow the chart to generate appropriate manifests for all the latest resources it supports via the `--api-versions`
and `--kube-version` flags.

Note that when used from ArgoCD, the `KUBE_VERSION` and `KUBE_API_VERSIONS` environment variables are set by ArgoCD
and Nyl will use them if available to avoid making an extra query to the Kubernetes API server. For more information,
see [ArgoCD Build Environment](https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/).

## Lookups

Nyl provides a `lookup()` function that allows the Helm chart to query the Kubernetes API server for an existing
resource to use in the chart. This is an optional feature that your manifests may simply decide not to rely on,
however it is a powerful feature to pass and transform values from existing resources.

With the new external destination cluster support, lookups will automatically query the correct cluster based on your
ArgoCD Application configuration.

TODO: Implement security to prevent lookups for resources that the corresponding ArgoCD project has no access to.
This will require a safe evaluation language instead of Python `eval()`.
