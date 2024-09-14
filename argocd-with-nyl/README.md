# nyl/argocd-with-nyl

This is a simple Nyl Kubernetes manifest to install ArgoCD with Nyl as a Config Management Plugin. The `argocd.yaml`
file here should serve as a starting point for bootstrapping your own ArgoCD instance.

## Goals

* Bootstrap an ArgoCD instance with Nyl as a Config Management Plugin from zero to fully functional in a single command.
* Have ArgoCD immediately own its own installation after bootstrapping.
* If anything goes wrong, be able to easily re-run the command to get back to a fully functional state.
* Demonstrate using SOPS to inject secrets into manifests and Helm chart values.

## Usage

You may want to modify the file to suit your needs before proceeding, for example to

* Configure ArgoCD to use OIDC for authentication.
* Configure ArgoCD to use an Ingress.
* Point ArgoCD to your own Git repository (this is required for ArgoCD to own its own installation after bootstrapping).
* Adjust the `nyl/argocd-cmp` image version.

Once you are ready, run the following command to bootstrap ArgoCD:

    $ nyl crds | kubectl apply -f -
    $ nyl template argocd.yaml --apply

Note that the `nyl-project.toml` is empty here, but it helps ArgoCD to automatically detect that the Nyl Config
Management Plugin should be used for this application.

## Project layout

The ArgoCD plugin will run `nyl template .` in this directory to generate the manifests for ArgoCD to apply. Nyl will
consider all YAML files (with the `.yaml` suffix, not `.yml`) in the directory (not recursively) as part of the project,
_excluding_ any files that begin with `nyl-`, `.` or `_`.

```
.envrc              -- Exports the SOPS_AGE_KEY so you can decrypt the secrets locally.
                       IMPORTANT: This specific setup is for demonstration purposes only. Do not use this in production.
                       Keep your secrets safe!
.secrets.yaml       -- Encrypted secrets file for SOPS. This file is encrypted with the SOPS_AGE_KEY in .envrc.
.sops.yaml          -- SOPS configuration file to specify the encryption method and the public key to use.
argocd.yaml         -- The main Nyl manifest file for ArgoCD that creates the argocd Namespace, the argocd-nyl-env
                       Secret, instantiates the ArgoCD Helm chart and creates the ArgoCD application to manage itself
                       after bootstrapping.
nyl-project.toml    -- Empty file that signals to ArgoCD that the Nyl Config Management Plugin should be used for this
                       application. This may have some project-specific configuration, but in this case it is empty.
nyl-secrets.toml    -- Tells Nyl to lookup secrets in the .secrets.yaml via SOPS when rendering the manifests that call
                       the `secrets.get(<key>)` function.
```

Note that configuration files may also be formatted as TOML (`.toml`) or JSON (`.json`).
