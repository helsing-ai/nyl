# Secrets

You can connect Nyl with various secret providers to retrieve external or encrypted data that can be used in your
templates. This is useful for keeping sensitive data out of your configuration files and ensuring that they are not
accidentally committed to a version control system.

## Configuration

Secret providers are configured in a `nyl-secrets.<ext>` file that is located in the current working directory or any of
its parent directories. Secret providers may also be defined in a [Project configuration file](./projects.md), though
the file closer to the working directory will take precedence.

There is no "global" way to define a secrets provider, as secrets are considered project-specific.

As with other configuration file types, the file extension can be `.toml`, `.yaml`, or `.json`.

The configuration contains any number of named secret providers. When not specified otherwise, Nyl will assume that the
provider to use is named `default`. The provider to use can be overriden by passing the corresponding CLI option to
respective Nyl commands or by setting the `NYL_SECRETS` environment variable.

## Inspecting secret providers

You can inspect secret providers using the `nyl secrets` command.

```
nyl secrets list            List the keys for all secrets in the provider.
nyl secrets get <key>       Get the value of a secret as JSON.
```

## Templating

Secrets are made available to templates using the `secrets.get()` function. The function takes a single argument, the
key of the secret to retrieve.

__Example__

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
type: Opaque
stringData:
  password: ${{ secrets.get("my-password") }}
```

## CLI

The `nyl secrets` command allows you to interact with the configured secret provider(s).

```
 Usage: nyl secrets [OPTIONS] COMMAND [ARGS]...                                 
                                                                                
 Interact with the secrets providers configured in `nyl-secrets.yaml`.          
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --provider        TEXT  The name of the configured secrets provider to use.  │
│                         [env var: NYL_SECRETS]                               │
│                         [default: default]                                   │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ get     Get the value of a secret as JSON.                                   │
│ list    List the keys for all secrets in the provider.                       │
│ set     Set the value of a secret.                                           │
│ unset   Unset the value of a secret.                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Provider: [Sops]

  [Sops]: https://github.com/getsops/sops

Allows you to retrieve secrets from a [Sops] encrypted file. For a GitOps workflow, the file must be commited to the
same repository to ensure that Nyl has access to it when it is invoked as an ArgoCD Config Management plugin. You also
must have the `sops` program installed.

__Example__

=== "TOML"

    ```toml title="nyl-secrets.toml"
    [default]
    type = "sops"
    path = "../secrets.yaml"
    ```

=== "YAML"

    ```yaml title="nyl-secrets.yaml"
    default:
      type: sops
      path: ../secrets.yaml
    ```

=== "JSON"

    ```toml title="nyl-secrets.json"
    {
      "default": {
        "type": "sops",
        "path": "../secrets.yaml"
      }
    }
    ```

The secrets will be decoded using the `sops` program, hence all the typical ways to configure Sops and how it decrypts
files apply. The `path` field is relative to the location of the `nyl-secrets.yaml` file.

---

## Provider: [Vault](https://www.vaultproject.io/)

Allows you to retrieve secrets from a HashiCorp Vault server using the KV secrets engine v2. This provider is designed
to work securely in multi-tenant environments and integrates with both local development and ArgoCD deployments.

### Authentication

The provider supports two authentication methods:

- **JWT Authentication (ArgoCD context)**: When running in ArgoCD, the provider authenticates using the Kubernetes
  service account JWT token mounted at `/var/run/secrets/kubernetes.io/serviceaccount/token`. This enables secure
  multi-tenant deployments where each application's workload identity is used to access only its authorized secrets.

- **Token Authentication (Local development)**: When running locally, the provider uses the token stored in
  `~/.vault-token` (obtained via `vault login`).

The provider automatically detects the execution context by checking for ArgoCD environment variables.

### Nested Keys and Dot Notation

The Vault provider supports nested structures through dot notation, similar to the SOPS provider:

- `"database"` retrieves the entire secret stored at the `database` path
- `"database.password"` retrieves the `password` field from the `database` secret
- `"database.credentials.username"` retrieves deeply nested fields

### Configuration Options

- `url` (required): The URL of the Vault server (e.g., `https://vault.example.com:8200`)
- `mount_point` (optional): The mount point of the KV secrets engine. Default: `secret`
- `path` (optional): Path prefix within the KV secrets engine. For example, if `path` is `myapp/`, secrets will be
  retrieved from `secret/data/myapp/...`
- `jwt_role` (optional): The Vault role to use for JWT authentication when running in ArgoCD. Required for JWT
  authentication.
- `namespace` (optional): The Vault namespace to use (Vault Enterprise feature only)

__Example__

=== "TOML"

    ```toml title="nyl-secrets.toml"
    [default]
    type = "vault"
    url = "https://vault.example.com:8200"
    mount_point = "secret"
    path = "myapp/"
    jwt_role = "nyl-argocd-role"
    ```

=== "YAML"

    ```yaml title="nyl-secrets.yaml"
    default:
      type: vault
      url: https://vault.example.com:8200
      mount_point: secret
      path: myapp/
      jwt_role: nyl-argocd-role
    ```

=== "JSON"

    ```json title="nyl-secrets.json"
    {
      "default": {
        "type": "vault",
        "url": "https://vault.example.com:8200",
        "mount_point": "secret",
        "path": "myapp/",
        "jwt_role": "nyl-argocd-role"
      }
    }
    ```

### Security Considerations

When using Vault in a multi-tenant ArgoCD environment:

1. Configure Vault to trust the Kubernetes cluster's JWT issuer
2. Create a Vault role for each application or team with appropriate policies
3. Bind the Vault role to the ArgoCD application's service account
4. Ensure the `jwt_role` in the Nyl configuration matches the Vault role
5. Use Vault policies to restrict access to only the necessary secrets

---

## Provider: [KubernetesSecret](https://kubernetes.io/docs/concepts/configuration/secret/)

Allows you to point to a Kubernetes Secret as a source for secrets. Since Kubernetes secret values must be strings,
this provider does not currently support nested keys, although it could be made possible by assuming TOML/YAML/JSON
format for the Kubernetes `Secret` keys in the `data` field.

The secret provider will use the same Kubernetes context that is configured in Nyl via [Profiles](./profiles.md).

__Example__

=== "TOML"

    ```toml title="nyl-secrets.toml"
    [default]
    type = "KubernetesSecret"
    name = "nyl-secrets"
    namespace = "default"
    ```

=== "YAML"

    ```yaml title="nyl-secrets.yaml"
    default:
      type: KubernetesSecret
      name: nyl-secrets
      namespace: default
    ```

=== "JSON"

    ```toml title="nyl-secrets.json"
    {
      "default": {
        "type": "KubernetesSecret",
        "name": "nyl-secrets",
        "namespace": "default"
      }
    }
    ```
