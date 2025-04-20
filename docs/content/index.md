---
title: Home
---

# Welcome to the Nyl documentation

Nyl is a flexible configuration management tool for Kubernetes resources that can be used to generate and deploy
applications directly via the command-line and via an [ArgoCD ConfigManagementPlugin][CMP].

  [CMP]: https://argoproj.github.io/argo-cd/operator-manual/config-management-plugins/

## Features

- **Usability**: Define your deployments once and let ArgoCD apply them, or apply the same deployment from the CLI when you
  need to break the glass without having to twist and warp your configuration for the occasion.

- **End-to-end configuration**: Not only codify your deployment configuration, but also how to connect to your cluster
  when you use the CLI. From using the default kubeconfig, to connecting to your cluster via an SSH tunnel, Nyl got you.

- **Powerful templating**: Load and inject secrets from external sources, instantiate Helm charts, post-process your
  manifests with Kyverno policies, streamline and standardize recurring configuration with Nyl components, lookup
  existing objects in the target cluster, etc.
