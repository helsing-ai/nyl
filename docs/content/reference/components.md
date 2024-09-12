# Components

Nyl components are effectively templates that you can instantiate them similar to standard Kubernetes resources. They
are treated in a way similar to CRDs, only that they will never to pushed to the Kubernetes API server and instead be
replaced throuhg a first reconcilation phase during `nyl template`.

## How Nyl looks for components

Nyl by default looks for components in a `components/` directory relative to your `nyl-project.yaml` (or relative to
your current working directory if there is no `nyl-project.yaml`). You can also override the path where Nyl looks in
the `nyl-project.yaml`:

```yaml title="nyl-project.yaml"
components_path: ../../components
```

## Component directory structure

A component must exist in a directory relative to the `components_path` in a path formatted as `{apiVersion}/{kind}`.
Hence, a typical project structure could look like this:

```
/
    components/
        example.org/
            v1/
                MyComponent/
                    [component definition]
    nyl-project.yaml
    myapp.yaml
```

The `[component definition]` must be a type of component Nyl understands. Currently, it only supports Helm charts.

## Using components

In your application manifests, you can instantiate a component by declaring it similar to a standard
Kubernetes resource. Nyl will try to lookup if that component exists and then instantiate it, or otherwise
leave the resource untouched.

```yaml title="myapp.yaml"
apiVersion: example.org/v1
kind: MyComponent
metadata:
    name: mycomponent
spec:
    key: value
```

## Component resource metadata

The component's `metadata` field will be passed to the Helm values. This allows forwarding annotations and labels, if any.

## Tips & tricks

You can use `nyl new component example.org/v1 MyComponent` to create the boilerplate for a new Nyl component.
Currently this is synonymous to calling `nyl new chart {components_path}/example.org/v1/MyComponent`.
