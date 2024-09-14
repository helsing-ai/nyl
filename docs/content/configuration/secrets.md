# Secrets

!!! note
    While we call them secrets for simplicity, data retrieved from secret providers must not necessarily be sensitive
    in nature.

The `nyl-secrets.yaml` file is used to define how to connect to a secret provider and retrieve secrets. The file is
located in the current working directory or any of its parent directories. The file is considered project-specific,
hence it is **not** searched in a global configuration directory.

## Provider: [Sops]

  [Sops]: https://github.com/getsops/sops

Allows you to retrieve secrets from a [Sops] encrypted file. For a GitOps workflow, the file must be commited to the
same repository to ensure that Nyl has access to it when it is invoked as an ArgoCD Config Management plugin. You also
must have the `sops` program installed.

__Example__

```yaml title="nyl-secrets.yaml"
type: sops
path: ../secrets.yaml
```

The secrets will be decoded using the `sops` program, hence all the typical ways to configure Sops and how it decrypts
files apply. The `path` field is relative to the location of the `nyl-secrets.yaml` file.

!!! todo
    Give a recommendation on how to best configure ArgoCD with a private key for Sops, and how to use the public key
    for encrypting secrets locally before committing them to the repository.

## Inspecting secret providers

You can inspect secret providers using the `nyl secrets` command.

```
nyl secrets list            List the keys for all secrets in the provider.
nyl secrets get <key>       Get the value of a secret as JSON.
```
