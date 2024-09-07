# ArgoCD plugin debugging

## Logging

The ArgoCD plugin produces per-project/application logs in the `/var/log` directory of the `nyl-v1` container in the
`argocd-repo-server` pod. These logs are often much easier to inspect than the output the template rendering fails
and ArgoCD reports stderr to the UI.
