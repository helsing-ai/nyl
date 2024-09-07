# ArgoCD plugin debugging

## Logging

The ArgoCD plugin produces per-project/application logs in the `/var/log` directory of the `nyl-v1` container in the
`argocd-repo-server` pod. These logs are often much easier to inspect than the output the template rendering fails
and ArgoCD reports stderr to the UI.

At the start of each invokation of Nyl, the command will debug-log some useful basic information:

* The command-line used to invoke Nyl.
* The current working directory.
* All Nyl-relevant environment variables (such that start with `ARGOCD_`, `NYL_` and `KUBE_`).
