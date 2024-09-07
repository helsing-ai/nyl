# Environment variables

This page summarizes all environment variables that are used by Nyl.

- `NYL_PROFILE` &ndash; The name of the profile to use as defined in the closest `nyl-profiles.yaml` configuration file.
  Used by: `nyl profile`, `nyl template`, `nyl tun`.
- `NYL_STATE_DIR` &ndash; The directory where Nyl stores its state, such as current profile data, which may include
  fetched Kubeconfig files, downloaded Helm charts and cloned repositories, etc. Defaults to `.nyl` relative to the
  `nyl-project.yaml` or the current working directory. Used by: `nyl template`.
- `KUBE_VERSION` &ndash; The version of the Kubernetes cluster. If this is not set, Nyl will try to query the Kubernetes
  API server to determine the version. When used as an ArgoCD plugin, this variable is usually available
  [^ArgoBuildEnv]. Used by: `nyl template`.
- `KUBE_API_VERSIONS` &ndash; A comma-separated list of all available API versions in the cluster. If this is not set,
  Nyl will try to query the Kubernetes API server to determine the versions. When used as an ArgoCD plugin, this
  variable is usually available [^ArgoBuildEnv]. Used by: `nyl template`.

[^ArgoBuildEnv]: See [ArgoCD Build Environment](https://argo-cd.readthedocs.io/en/stable/user-guide/build-environment/).
