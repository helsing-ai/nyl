# Environment variables

This page summarizes all environment variables that are used by Nyl.

## General

- `NYL_ARGS` &ndash; Additional command-line arguments to append to the Nyl invocation. Use with care, as options
  accepted by a parent command are not accepted in a subcommand, and these arguments are only ever append to the
  argument list.
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

## Build-environment variables

> The following variables are supported for they are provided by [ArgoCD as Build Environment Variables][^ArgoBuildEnv].

- `KUBE_VERSION` &ndash; The version of the Kubernetes cluster. If this is not set, Nyl will try to query the Kubernetes
  API server to determine the version. When used as an ArgoCD plugin, this variable is usually available
  [^ArgoBuildEnv]. Used by: `nyl template`.
- `KUBE_API_VERSIONS` &ndash; A comma-separated list of all available API versions in the cluster. If this is not set,
  Nyl will try to query the Kubernetes API server to determine the versions. When used as an ArgoCD plugin, this
  variable is usually available [^ArgoBuildEnv]. Used by: `nyl template`.

## Plugin variables

> ArgoCD permits passing environment variables to CustomManagementPlugins. These get prefixed with `ARGOCD_ENV` to
> ensure that only specifically supported variables can be set. The following such variables are supported by Nyl:

- `ARGOCD_ENV_NYL_ARGS` &ndash; Same as `NYL_ARGS`, but is taken into account after.
- `ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT` &mdash; This variable is only recognized by `nyl template` when the only positional argument
  it receives is `.` (i.e. the current working directory). The variable should be a comma-separated list of filenames
  that should be treated as if the files were passed as arguments to `nyl template` instead. This is used for the Nyl
  ArgoCD plugin to allow specifying exactly which files should be templated as part of an ArgoCD application.

[^ArgoBuildEnv]: See [ArgoCD Build Environment](https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/).
