# nyl

Nyl is a versatile tool for generating Kubernetes manifests from a simple YAML configuration, encouraging
consistent and reusable deployment configurations, project layouts and operational workflows.

## Installation

Requires Python 3.11 or newer.

    $ uvx nyl

For some features, additional programs must be available:

* [kubectl](https://kubernetes.io/de/docs/reference/kubectl/) for most operations
* [kyverno](https://kyverno.io/docs/kyverno-cli/) when using the Nyl `PostProcessor` resource
* [sops](https://github.com/getsops/sops) when using the SOPS secrets provider

## Local development

Install the project with [Uv](https://docs.astral.sh/uv/).

    $ uv sync

## Tracking upstream information

* Discussion around ArgoCD supporting Helm lookups (maybe with Project-level service account?), see
  https://github.com/argoproj/argo-cd/issues/5202#issuecomment-2088810772
