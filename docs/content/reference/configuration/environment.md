# Environment variables

This page summarizes all environment variables that are used by Nyl.

- `NYL_LOG_LEVEL` &ndash; The log level to use if `--log-level` is not specified. Defaults to `info`. Used by: `nyl`.
- `NYL_PROFILE` &ndash; The name of the profile to use as defined in the closest `nyl-profiles.yaml` or
  `nyl-project.yaml` configuration file. Used by: `nyl profile`, `nyl template`, `nyl tun`.
- `NYL_SECRETS` &ndash; The name of the secrets provider to use as defined in the closest `nyl-secrets.yaml` or
  `nyl-project.yaml` configuration file. Used by: `nyl secrets`, `nyl template`.
- `NYL_STATE_DIR` &ndash; The directory where Nyl stores its state, such as current profile data, which may include
  fetched Kubeconfig file. Defaults to `.nyl` relative to the `nyl-project.yaml` or the current working directory.
  Used by: `nyl profile`, `nyl template`, `nyl tun`.
- `NYL_CACHE_DIR` &ndash; The directory where Nyl stores its cache, such as downloaded Helm charts and cloned
  repositories. Defaults to `cache/` relative to the `NYL_STATE_DIR`. Used by `nyl template`.
- `ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT` &mdash; This variable is only recognized by `nyl template` when the only positional argument
  it receives is `.` (i.e. the current working directory). The variable should be a comma-separated list of filenames
  that should be treated as if the files were passed as arguments to `nyl template` instead. This is used for the Nyl
  ArgoCD plugin to allow specifying exactly which files should be templated as part of an ArgoCD application.
- `KUBE_VERSION` &ndash; The version of the Kubernetes cluster. If this is not set, Nyl will try to query the Kubernetes
  API server to determine the version. When used as an ArgoCD plugin, this variable is usually available
  [^ArgoBuildEnv]. Used by: `nyl template`.
- `KUBE_API_VERSIONS` &ndash; A comma-separated list of all available API versions in the cluster. If this is not set,
  Nyl will try to query the Kubernetes API server to determine the versions. When used as an ArgoCD plugin, this
  variable is usually available [^ArgoBuildEnv]. Used by: `nyl template`.

[^ArgoBuildEnv]: See [ArgoCD Build Environment](https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/).
