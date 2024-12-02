# Changelog

## 0.6.0

* Upgraded `argocd-cmp-server` in `nyl/argocd-cmp` container image to `v2.13.1` (see [#46](https://github.com/NiklasRosenstein/nyl/pull/46))
* Re-introduce `settings.generate_placeholders` in `nyl-project.toml`, but warn if it is used. Enabling the option will have the
    same effect as setting `on_lookup_failure = "CreatePlaceholder"` and take precedence over the original value of `on_lookup_failure`.

## 0.5.1

* Add Nix flake
* Docs: Add missing API docs for `nyl.secrets.kubernetes`

## 0.5.0

* Add the [`KubernetesSecret`](./reference/configuration/secrets.md#provider-kubernetessecret) secret provider
* Add the `ntyl secrets set` and `nyl secrets unset` commands
* Breaking: Replace the `settings.generate_placeholders` option with `settings.on_lookup_failure`

## 0.4.0

* Automatically replace the host in Kubeconfig `server` field if it is set to `localhost`, `0.0.0.0` or `127.0.0.1`
    when a Kubeconfig is retrieved via SSH (saving you to configure `replace_apiserver_hostname` when sourcing a
    Kubeconfig from a K3s/RKE2 cluster via SSH).
* Add `port` and `sudo` option to `KubeconfigFromSsh` config

## 0.3.0

* Add [`PostProcessor`](./reference/templating/inlining/postprocessor.md) inline resource which supports applying
    Kyverno policies to the generated resources.
* Fixed a bug in the construction of the local Helm chart path when referencing a Helm chart in a Git repository.
