# Secret injection

!!! danger
    When using secret injection with Nyl, you must make sure that you are aware of the risk profile for unintentionally
    revealing a secret in ArgoCD, which only masks out the data for actual Kubernetes `Secret` resources. Any other
    resource that contains the secret will be rendered in plain text.

Secrets can be injected into your application configuration using the `secrets.get(key)` function. The `key` is the name
of the secret as it is stored in the cluster. You can inspect all available keys of your configured secrets provider
using the `nyl secrets list` command.

## Example

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
stringData:
  my-secret: ${{ secrets.get("my-secret") }}
```

## Syncing secret updates

When a secret is injected via Nyl and the secret is updated in the secrets provider, you must re-run `nyl template`
and apply the updated configuration to the cluster. When using ArgoCD, this can happen automatically simply by
re-syncing the application (or enabling auto-sync as the change to the secret value will be considered as drift to
the desired configuration).

!!! todo

    ArgoCD caches generated manifests so there may be a time delay between the secret update and ArgoCD fully
    re-materilizing the desired manifests with the updated secret being taken into account. What's the cache TTL,
    can it be changed/flushed?

    (A "hard refresh" usually works, but for automatic drift reconcilation when secrets update, having a lower TTL
    is important).
