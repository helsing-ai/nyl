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
- `NYL_TEMPLATE_JOBS` &ndash; The maximum number of jobs to use for parallel evaluation of Nyl inline resources
  when running `nyl template`. If not set, and not specified with the `-j, --jobs` option, an adequate number of jobs
  will be selected automatically.

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

- `ARGOCD_ENV_NYL_PROFILE` &ndash; Same as `NYL_PROFILE`, only that the profile's connection details will be ignored.
  This should be used to pass the profile name to the Nyl plugin, as there is no way for it to automatically understand
  what profile to use if the `default` profile does not apply. This variable is only recognized by the `nyl template`
  command. The `NYL_PROFILE` variable takes precedence.
- `ARGOCD_ENV_NYL_ARGS` &ndash; Same as `NYL_ARGS`, but is taken into account after.
- `ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT` &mdash; This variable is only recognized by `nyl template` when the only positional argument
  it receives is `.` (i.e. the current working directory). The variable should be a comma-separated list of filenames
  that should be treated as if the files were passed as arguments to `nyl template` instead. This is used for the Nyl
  ArgoCD plugin to allow specifying exactly which files should be templated as part of an ArgoCD application.

[^ArgoBuildEnv]: See [ArgoCD Build Environment](https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/).

## Daemon mode

- `NYL_DAEMON_LOG_STDERR` &ndash; If set to `1`, the daemon in client mode will forward stderr output of the
  template operation to the CMP plugin's stderr output. This may be useful for debugging purposes, but the same output
  can also be inspected in the daemon container's logs. This is disabled by default to not show the stderr output
  in the error message in the ArgoCD Web UI when the plugin fails.
- `NYL_DAEMON_SOCK` &ndash; This variable is only used by the ArgoCD CMP `plugin.yaml`. If set, it tells the plugin
  to use the `nyl-daemon` in client mode instead of running `nyl template` directly and connect to the Nyl daemon using
  a Unix socket as specified in the variable value.
