---
weight: 5
---

# Inlining

Nyl supports inlining of Kubernetes resources generated from templates in your configuration. Resources that are
inlined by Nyl are typically in the `inline.nyl.io/v1` API group, however Nyl also has the concept of
[components](./components.md) which effectively allow you to define your own API groups and resource kinds for
inlined resources.

## Helm charts

Nyl currently only supports inlining of Helm charts. Helm charts are inlined by specifying a `HelmChart` resource in
your configuration. Just like any other resource, the Helm chart resource values can be templated using Nyl's
[structured templating](../templating/basics.md) (for example to inject secrets), and are then rendered to Kubernetes
resources that are inlined in your configuration.

__Example__

```yaml 
apiVersion: inline.nyl.io/v1
kind: HelmChart
metadata:
  name: my-release
  namespace: default
spec:
  chart:
    repository: https://charts.bitnami.com/bitnami
    name: nginx
  values:
    controller:
      service:
        type: LoadBalancer
```

### Comparison to native ArgoCD Helm applications

Nyl may look similar to Helm in the sense that it allows for templating YAML files. However, there are some important
differences between the two that make Nyl the better choice for defining applications in a GitOps repository.

#### Passing secrets more safely

Values for ArgoCD Helm applications are either stored in a values-file in the repository (in plain-text) or in the
`valuesObject` configuration of the ArgoCD `Application` spec (again, in plain-text). The `valuesObject` like standard
Kubernetes `Secret` resources when inspected via the ArgoCD UI, which makes storing the secrets are part of the
application spec undesirable.

!!! danger

    You must still be careful when using Nyl to inject secrets into Helm charts. The Helm chart may pass the secret
    value into a resource that is not a `Secret`, which would then be rendered in plain-text in the cluster when
    inspected in ArgoCD or via `kubectl`.

#### Combining multiple Helm charts

An ArgoCD application supports only a single Helm chart. If you need to deploy multiple Helm charts as part of a single
application, you would need to create a Helm chart that includes all the other charts. However, this can lead to a
complicated setup that is hard to maintain: It either requires you to repeat the same values in multiple places, or
all subcharts support `globals`.

#### Secret injection

Natively, ArgoCD applications do not support injecting secrets into the Helm chart values. With Nyl, you can connect
to a secrets provider and inject secrets into the generated resources or the value of a Helm chart parameter. Your
YAML template becomes the glue code for propagating secrets from the point of origin into your Kubernetes cluster
and application.

In many cases you can work around this limitation by placing a `Secret` resource into your cluster, either manually
or by other means (such as using [external-secrets]), but this does not cover the use case for Helm charts that require
a secret, or more generally, an external parameter, in a place where an existing secret cannot be configured (e.g.
either because the chart simply does not support it or because it needs to be in a specific place/format). This is
most commonly an issue when deploying third-party applications from Helm charts.

  [external-secrets]: https://external-secrets.io/latest/

#### Pipelining between applications (TODO)

Nyl supports looking up information in the cluster at time of rendering the resources. This allows for iteratively
reconciling resources in the cluster that depend on each other. For example, it is not uncommon to have an application
generate a `Secret` that later needs to be transformed and piped into another Helm chart.

!!! danger
    When this feature is enabled, Nyl would allow lookups across the entire cluster (or the resources that the
    ArgoCD service account has access to). This is a powerful feature that can be used to build complex applications,
    but it also comes with a security risk when a cluster is shared between multiple teams.

!!! todo
    Explain how this feature works and how to enable it.
