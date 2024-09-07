# Cluster connectivity

Nyl may need to reach out to the Kubernetes API for various reasons, some of which are fundamental and others are
optional.

When using Nyl as an ArgoCD plugin, to enable the plugin to reach out to the Kubernetes API, you must configure the
`argocd-repo-server` service account with the necessary permissions. See [ArgoCD Plugin](./argocd-plugin.md) for more
information.

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

TODO: Implement security to prevent lookups for resources that the corresponding ArgoCD project has no access to.
This will require a safe evaluation language instead of Python `eval()`.
