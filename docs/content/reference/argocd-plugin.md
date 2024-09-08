# ArgoCD Plugin

  [0]: https://argo-cd.readthedocs.io/en/latest/operator-manual/config-management-plugins/

This page describes Nyl's integration as an [ArgoCD ConfigManagementPlugin][0].

## Installation

Config management plugins are installed as additional containers to the `argocd-repo-server` Pod. They launch the
`argocd-cmp-server` binary and communicates with ArgoCD over gRPC via a socket file shared between the repo-server
and the plugin container under `/home/argocd/cmp-server/plugins`.

We recommend the following configuration:

```yaml title="argocd-values.yaml"
repoServer:
  extraContainers:
    - name: nyl-v1
      image: ghcr.io/niklasrosenstein/nyl/argocd-cmp:{{ NYL_VERSION }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
      volumeMounts:
        - mountPath: /var/run/argocd
          name: var-files
        - mountPath: /home/argocd/cmp-server/plugins
          name: plugins
        - mountPath: /tmp
          name: cmp-tmp
      envFrom:
        - secretRef:
            name: argocd-nyl-env
      env:
        - name: NYL_CACHE_DIR
          value: /tmp/nyl-cache
        - name: NYL_LOG_LEVEL
          value: info
  clusterRoleRules:
    enabled: true
  volumes:
    - name: cmp-tmp
      emptyDir: {}
```

!!! warning

    The `clusterRoleRules.enabled=true` option enables the plugin to access the Kubernetes API. This is necessary for
    various Nyl features to function correctly (such as lookups, see [Cluster connectivity](./cluster-connectivity.md)).
    If you do not wish to grant the plugin access to the Kubernetes API, you must disable this option and ensure that
    your manifests do not rely on features that require API access.

## One file per application

ArgoCD applications do not permit to point their `source.path` field to a file within a repository, it must be a
directory. For this, Nyl accepts a `NYL_CMP_TEMPLATE_INPUT` environment variable that can be a comma-separate list
of filenames that you would pass to `nyl template` as arguments. Nyl will then ignore the default `.` argument
(pointing to the current directory, which is the directory specified with `source.path`) and use the files specified
via the environment variable instead.

## Debugging the plugin

The ArgoCD plugin produces per-project/application logs in the `/var/log` directory of the `nyl-v1` container in the
`argocd-repo-server` pod. These logs are often much easier to inspect than the output the template rendering fails
and ArgoCD reports stderr to the UI.

At the start of each invokation of Nyl, the command will debug-log some useful basic information:

* The command-line used to invoke Nyl.
* The current working directory.
* All Nyl-relevant environment variables (such that start with `ARGOCD_`, `NYL_` and `KUBE_`).

At the end Nyl will also print the command-line again as well as the time it took for the command to complete.
Note that in order to see these logs you should set the `NYL_LOG_LEVEL` environment variable to `debug`.
