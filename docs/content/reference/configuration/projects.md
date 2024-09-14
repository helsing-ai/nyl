# Projects

## Configuration

*Todo*

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

* [Components](../components.md)
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
