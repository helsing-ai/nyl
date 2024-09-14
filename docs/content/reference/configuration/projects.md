# Projects

A Nyl project is a collection of files that together describe a set of Kubernetes resources that are typically deployed
to at least one Kubernetes cluster and source secrets from zero or more secrets provider. Kubernetes resources are
defined in YAML files and may be templated using [Nyl's structured templating](../templating/basics.md) or as Helm
charts. Helm charts may be used as [Nyl components](../templating/components.md).

## Configuration

Projects are defined in a `nyl-project.<ext>` file that is located in the current working directory or any of its parent
directories. A project configuration file is not required to use Nyl, however it is recommended to set various project
settings, such as the search path for Helm charts and [Nyl components](../templating/components.md), whether to generate
[Nyl ApplySets](../applysets.md), etc.

A project configuration file may also contain the configuration for secrets providers and profiles, though if any
configuration file closer to the current working directory for secrets providers or profiles is found, it will take
precedence.

## Example

The following example demonstrates a simple project configuration file that sets the search path for Helm charts and
Nyl components, enables the generation of ApplySets, and defines a default secrets provider.

```toml title="nyl-project.toml"
[settings]
generate_applysets = true
search_path = ["packages"]

[profiles.default.kubeconfig]
type = "local"
context = "my-cluster"

[secrets.default]
type = "sops"
path = "secrets.yaml"
```

## Project structure

Nyl is not too opinionated about the project structure, but it was built with support for a certain structure in mind.
The following is a suggestion for how to structure your project.

### Homogenous targets

With mostly homogenous clusters (e.g. referencing the same secrets, local helm charts, etc.), a typical project
structure may have all Nyl configuration files at the top-level.

If you're using ArgoCD, it's also common to further organize the cluster-specific configuration files in ArgoCD
project-specific directories. We recommend to self-manage ArgoCD only from the `default` project.

```
clusters/
└── my-cluster/
    ├── .envrc
    ├── default/
    │   └── argocd.yaml
    └── main-project/
        └── myapp.yaml
components/
nyl-project.toml
```

__Further reading__

* [Components](../templating/components.md)
* [ArgoCD ApplicationSet Example](../argocd-plugin.md#applicationset-example)

### Heterogenous targets

For more complex projects with multiple clusters that all look very different and reference differnt secrets, etc.,
you may want to move your Nyl configuration files closer to the cluster-specific configuration.

```
clusters/
└── main-cluster/
│   ├── .envrc
│   ├── default/
│   │   └── argocd.yaml
│   └── project-a/
│       └── myapp.yaml
└── my-other-cluster/
    ├── .envrc
    └── project-b/
        └── myapp.yaml
nyl-project.yaml
```

If you're using ARgoCD,  you can image `main-cluster` containing the ArgoCD instance that also deploys the
`my-other-cluster`.
