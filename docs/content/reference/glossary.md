# Glossary

  [Nyl-inline]: ./templating/inlining/overview.md

### Manifest

A manifest is a file that may define zero or more Kubernetes or [Nyl inline resources][Nyl-inline]. Nyl understands
individual manifests, i.e. YAML files, and certain behaviours operate on that level, such as Kubernetes Namespace
auto-filling and resource post-processing applying only to all resources defined in the same manifest as the
[`PostProcessor`](./templating/inlining/postprocessor.md).

### Profile

...

### Project

...

### Resource

A resource is a YAML document that follows the schema of a Kubernetes API resource or [Nyl inline resource][Nyl-inline].
An example would be a Kubernetes `ConfigMap`, `Deployment`, `Pod` or a Nyl `HelmChart` or `PostProcessor`.

### Secrets provider

...
