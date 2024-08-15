# nyl

Nyl is a versatile tool for generating Kubernetes manifests from a simple YAML configuration, encouraging
consistent and reusable deployment configurations, project layouts and operational workflows.

## Local development

This project uses the [PDM](https://pdm-project.org/latest/) package manager for Python. Start with
`$ pipx install pdm` followed by `$ pdm install --frozen-lockfile`.

## Tracking upstream information

* Discussion around ArgoCD supporting Helm lookups (maybe with Project-level service account?), see
  https://github.com/argoproj/argo-cd/issues/5202#issuecomment-2088810772
