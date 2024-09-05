# Introduction

Nyl provides various configuration files to customize different aspects of the application:

* **`nyl-profiles.yaml`** defines the profiles that describe how Nyl can make a connection to your Kubernetes
  cluster(s). It is often useful to commit this file into a project's repository to share the configuration with other
  team members, but you can also store it in your home directory.

    &rarr; [Read more about Profile configuration files](./profiles.md).

* **`nyl-secrets.yaml`** is project-specific, as it defines the secret provider where secret values can be sourced from
  in your Kubernetes manifests that are processed by Nyl. The secrets configuration is usually tied closely with a
  particular deployment environment. Nyl uses the closest configuration file to your project's working directory, hence
  this file may also be used to span multiple projects.

    &rarr; [Read more about Secrets configuration files](./secrets.md).

* **`nyl-project.yaml`**, as the name implies, is project-specific and defines the project's metadata and configuration.
  A project may yet span more than a single cluster.

    &rarr; [Read more about Project configuration files](./projects.md).

Nyl works particularly well with [Direnv] to simplify your workflow, particularly in multi-cluster deployment
environments. Use it to set `NYL_PROFILE` to ensure the right cluster is targeted and run `. <(nyl profile activate)`
to ensure immediate cluster connectivity when changing directories.

  [Direnv]: https://direnv.net/

Note that configuration files may also be formatted as TOML (`.toml`) or JSON (`.json`).

## Typical project structure

With mostly homogenous clusters (e.g. referencing the same secrets, local helm charts, etc.), a typical project
structure may have all Nyl configuration files at the top-level.

```
clusters/
└── my-cluster/
    ├── .envrc
    └── myapp.yaml
nyl-profiles.yaml
nyl-project.yaml
nyl-secrets.yaml
```

For more complex projects with multiple clusters that all look very different and reference differnt secrets, etc.,
you may want to move your Nyl configuration files closer to the cluster-specific configuration.

```
clusters/
├── my-cluster/
│   ├── .envrc
│   ├── nyl-secrets.yaml
│   └── myapp.yaml
└── my-other-cluster/
    ├── .envrc
    ├── nyl-secrets.yaml
    └── other-app.yaml
nyl-profiles.yaml
nyl-secrets.yaml
```
