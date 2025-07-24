# nyl

Nyl is a versatile tool for generating Kubernetes manifests from a simple YAML configuration, encouraging consistent and
reusable deployment configurations, project layouts and operational workflows.

## Installation

Requires Python 3.11 or newer.

    $ uvx nyl

For some features, additional programs must be available:

- [kubectl](https://kubernetes.io/de/docs/reference/kubectl/) for applying
- [helm](https://helm.sh/) for rendering Helm charts
- [kyverno](https://kyverno.io/docs/kyverno-cli/) ^1.13.x when using the Nyl `PostProcessor` resource
- [sops](https://github.com/getsops/sops) when using the SOPS secrets provider

## Local development

You can install the tools you need with [Mise](https://mise.jdx.dev/).

    $ mise install
    $ eval "$(mise activate)"

Install the project with [Uv](https://docs.astral.sh/uv/).

    $ uv sync

Use [Tire](https://github.com/NiklasRosenstein/tire/) tire for formatting, linting, type checking and unit tests.

    $ tire fmt [--check]
    $ tire lint
    $ tire check
    $ tire test

To live-preview the documentation, use

    $ mise run serve-docs

## Tracking upstream information

- Discussion around ArgoCD supporting Helm lookups (maybe with Project-level service account?), see
  https://github.com/argoproj/argo-cd/issues/5202#issuecomment-2088810772
