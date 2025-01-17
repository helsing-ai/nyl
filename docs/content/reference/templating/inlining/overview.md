---
title: Overview
---

# Inlining Overview

Nyl supports inlining of Kubernetes resources generated from templates in your configuration. Resources that are
inlined by Nyl are typically in the `inline.nyl.io/v1` API group, however Nyl also has the concept of
[components](../components.md) which effectively allow you to define your own API groups and resource kinds for
inlined resources.
