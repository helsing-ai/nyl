# ApplySets

[1]: https://kubernetes.io/blog/2023/05/09/introducing-kubectl-applyset-pruning/

[Kubernetes ApplySets][1] are a method of managing groups of Kubernetes resources for safely applying and pruning
resources in a cluster. Nyl provides basic support for ApplySets, allowing you to keep track of deployed resources
and prune resources as they are removed from your configuration.

Note that ApplySet support is experimental and has still has various issues. You can following the progress of the
feature in the [nyl#5](https://github.com/helsing-ai/nyl/issues/5).
