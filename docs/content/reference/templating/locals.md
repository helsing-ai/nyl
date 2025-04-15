# Local Variables

You may define a YAML object in your Kubernetes manifest that is used to define variables that can later be accessed
in the same manifest to achieve some level of DRY-ness. This is done by not setting any `apiVersion` or `kind`, and
instead just define variables prefixed with `$`. Variables can later be accessed using the `${{ locals.var }}`.

Note that expressions in values assigned to variables are not currently supported. This means that you cannot use e.g.
`${{ secrets.get("my-secret") }}` in the value of a variable, nor can you use `${{ locals.var }}`.

## Example

```yaml
# my-app.yaml
$name: my-app

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${{ locals.name }}
# ...
```

> Technically, such an object defining local variables can be defined anywhere in the manifest and more than once.
> By convention and to improve readability, it is recommended to define it at the top of the manifest. The object is not
> rendered in the final manifest.
