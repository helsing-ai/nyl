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

    $ nyl template argocd.yaml --apply

Note that the `nyl-project.yaml` is empty here, but it helps ArgoCD to automatically detect that the Nyl Config
Management Plugin should be used for this application.
