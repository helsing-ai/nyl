# Cluster connectivity

Nyl may need to reach out to the Kubernetes API for various reasons, some of which are fundamental and others are
optional.

## Kubernetes API versions

When Nyl invokes `helm template`, it must pass along a full list of all available API versions in the cluster to
allow the chart to generate appropriate manifests for all the latest resources it supports via the `--api-versions`
flag.

This is a fundamental requirement, which, to an extend, _unfortunately_, requires that Nyl has access to the Kubernetes
API server, even when used as an ArgoCD plugin. When using `helm install`, it will be Helm to make that query to the
Kubernetes API server to discover all API versions. When instantiating a Helm chart via ArgoCD, it is ArgoCD that will
make that request.

TODO: Implement connectivity to alternative destination clusters when run in ArgoCD and document how that works/what
extra steps must be done to configure Nyl+ArgoCD to work in such a setup.

## Lookups

Nyl provides a `lookup()` function that allows the Helm chart to query the Kubernetes API server for an existing
resource to use in the chart. This is an optional feature that your manifests may simply decide not to rely on,
however it is a powerful feature to pass and transform values from existing resources.

TODO: Implement security to prevent lookups for resources that the corresponding ArgoCD project has no access to.
This will require a safe evaluation language instead of Python `eval()`.
