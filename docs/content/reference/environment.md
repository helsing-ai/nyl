# Environment variables

This page summarizes all environment variables that are used by Nyl.

- `NYL_PROFILE` &ndash; The name of the profile to use as defined in the closest `nyl-profiles.yaml` configuration file.
  Used by: `nyl profile`, `nyl template`, `nyl tun`.
- `NYL_STATE_DIR` &ndash; The directory where Nyl stores its state, such as current profile data, which may include
  fetched Kubeconfig files, downloaded Helm charts and cloned repositories, etc. Defaults to `.nyl` relative to the
  `nyl-project.yaml` or the current working directory. Used by: `nyl template`.

