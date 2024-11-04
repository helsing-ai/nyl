# Profiles

Profiles allow you to tell Nyl how to connect to a Kubernetes cluster. They work in concert with traditional
"kubeconfig" and allow you to have a certain level of assurance you are targeting the expected cluster, as well as
providing additional connection methods (such as via SSH tunnel).

!!! warning "ArgoCD"

    Profiles are not required with ArgoCD, as the target cluster is defined in the ArgoCD application. Having a profile
    configuration in your repository when deploying with ArgoCD may have unintended consequences for the way Nyl
    interacts with the target cluster.

## Configuration

Profiles are defined in a `nyl-profiles.<ext>` file that is located in the current working directory or any of its
parent directories. Profiles may also be defined in a [Project configuration file](./projects.md), though the file
closer to the working directory will take precedence.

If no profile configuration is found this way, Nyl will look for a global configuration file in
`~/.nyl/nyl-profiles.<ext>`.

As with other configuration file types, the file extension can be `.toml`, `.yaml`, or `.json`.

The configuration contains any number of named profiles. When not specified otherwise, Nyl will assume that the profile
to use is named `default`. The profile to use can be overriden by setting the `NYL_PROFILE` environment variable, or
by passing the corresponding CLI option to respective Nyl commands.

## Profile definition

A profile describes:

1. How to obtain the kubeconfig for the target cluster.
2. (Optionally) How to connect to the target cluster via a tunnel.

The tunnel configuration is useful when the target cluster is not directly accessible from the machine running Nyl,
for example when the cluster is behind a firewall or on-premises but can be accessed via an SSH jump host.

## Example

The following example has Nyl fetch the kubeconfig from a remote machine via SSH, then open an SSH tunnel to the same
machine and use that to connect to the Kubernetes cluster.

=== "TOML"

    ```toml title="nyl-profile.toml"
    [default.kubeconfig]
    type = "ssh"
    sudo = false  # default, set to true to use `sudo cat <path>`
    user = "root"
    host = "mycluster.example.com"
    port = 22 # default
    path = "/etc/rancher/k3s/k3s.yaml"
    # replace_apiserver_hostname

    [default.tunnel]
    type = "ssh"
    user = "root"
    host = "mycluster.example.com"
    ```

=== "YAML"

    ```yaml title="nyl-profile.yaml"
    default:
      kubeconfig:
        type: ssh
        sudo: false
        user: root
        host: mycluster.example.com
        port: 22
        path: /etc/rancher/k3s/k3s.yaml
        replace_apiserver_hostname: null
      tunnel:
        type: ssh
        user: root
        host: mycluster.example.com
    ```

=== "JSON"

    ```json title="nyl-profile.json"
    {
      "default": {
        "kubeconfig": {
          "type": "ssh",
          "sudo": false,
          "user": "root",
          "host": "mycluster.example.com",
          "port": 22,
          "path": "/etc/rancher/k3s/k3s.yaml",
          "replace_apiserver_hostname": null
        },
        "tunnel": {
          "type": "ssh",
          "user": "root",
          "host": "mycluster.example.com"
        }
    }
    ```

In the following example, the kubeconfig is also fetched via SSH, but the server hostname is replaced with one that
is reachable from your local machine.

=== "TOML"

    ```toml title="nyl-profile.toml"
    [default.kubeconfig]
    type = "ssh"
    user = "root"
    host = "mycluster.example.com"
    path = "/etc/rancher/k3s/k3s.yaml"
    replace_apiserver_hostname = "reachable-address.com"
    ```

=== "YAML"

    ```yaml title="nyl-profile.yaml"
    default:
      kubeconfig:
        type: ssh
        user: root
        host: mycluster.example.com
        path: /etc/rancher/k3s/k3s.yaml
        replace_apiserver_hostname: reachable-address.com
    ```

=== "JSON"

    ```json title="nyl-profile.json"
    {
      "default": {
        "kubeconfig": {
          "type": "ssh",
          "user": "root",
          "host": "mycluster.example.com",
          "path": "/etc/rancher/k3s/k3s.yaml",
          "replace_apiserver_hostname": "reachable-address.com"
        }
    }
    ```

!!! note

    When retrieving a Kubeconfig via SSH that has `127.0.0.1`, `0.0.0.0` or `localhost` as the hostname in the `server`
    field, and `replace_apiserver_hostname` is not specified, Nyl will automatically replace it with the `host` field
    specified that was used to execute the remote command to read the Kubeconfig. This is because we expect the two
    hosts to be the same, and you cannot reach the Kubernetes API server through your local machine without using tunnel
    (which you can use, see [Tunnel management](#tunnel-management)).

If you are you are already setup with a kubeconfig file, you can specify the path to the file directly or have it
automatically use your `~/.kube/config` file/`KUBECONFIG` environment variable. You may specify the context to use
from that kubeconfig file which ensures Nyl interacts with the correct cluster, even if your
`kubectl config get-contexts` indicates a different current context.

=== "TOML"

    ```toml title="nyl-profile.toml"
    [default.kubeconfig]
    type = "local"
    context = "mycluster"
    ```

=== "YAML"

    ```yaml title="nyl-profile.yaml"
    default:
      kubeconfig:
        type: local
        context: mycluster
    ```

=== "JSON"

    ```json title="nyl-profile.json"
    {
      "default": {
        "kubeconfig": {
          "type": "local",
          "context": "mycluster"
        }
    }
    ```

!!! note "Implementation detail"

    Nyl ensures that the correct context is used when interacting with the target cluster, e.g. when using
    `nyl run -- kubectl` or using `nyl profile activate` by generating a temporary kubeconfig file that is stripped
    down to include only the specified context. You can use `nyl profile get-kubeconfig` to retrieve the path of the
    temporary kubeconfig file.

## Specification

!!! todo
    Include specification of configuration data model.

## Using a profile

All Nyl commands that interact with the cluster will use the profile specified by the `NYL_PROFILE` environment variable
or the one specified with the respective CLI option. If there is no profile configuration in your environment, Nyl will
fall back to the global Kubernetes configuration file (equivalent of having a `default` profile with `type: local` and
no `context` specified).

You can update your shell by source-ing the output of the `nyl profile activate` command to set the `KUBECONFIG`
and `KUBE_CONFIG_PATH` environment variables. (The latter is used for example for the Kubernetes Terraform provider).

```sh
$ nyl profile activate
export KUBECONFIG=/project/path/.nyl/profiles/default/kubeconfig.local
export KUBE_CONFIG_PATH=/project/path/.nyl/profiles/default/kubeconfig.local
$ . <(nyl profile activate)
```

[Direnv]: https://direnv.net/

??? note "Tip: Using Direnv"

    When working in a project, you can use [Direnv] to automatically set the environment variables when you `cd` into
    a directory that contains configuration corresponding to a specific Kubernetes cluster.

    ```sh title=".envrc"
    export NYL_PROFILE=myprofile
    . <(nyl profile activate)
    ```

If `NYL_PROFILE` is not set, Nyl will assume the default profile name is `default`.

## Tunnel management

The Nyl CLI will automatically manage tunnels to the target cluster by proxying through an SSH jump host. 
The tunnel will typically remain open unless it is explicitly closed by the user to reduce the overhead of
setting up the tunnel for each invocation of Nyl.

Tunnels can be managed manually using the `nyl tun` command. Tunnel state is stored globally in
`~/.nyl/tunnels/state.json`. Note that while you may have multiple `nyl-profiles.yaml` files on your
system, the tunnel state is stored globally, and such is the interaction with `nyl tun`.

```
nyl tun status               List all known tunnels.
nyl tun start <profile>      Open a tunnel to the cluster targeted by the profile.
nyl tun stop [<profile>]     Close all tunnels or the tunnel for a specific profile.
```
