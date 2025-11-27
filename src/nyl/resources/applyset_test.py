from nyl.resources.applyset import (
    ApplySet,
    ApplySetContext,
    NYL_ANNOTATION_LAST_APPLIED_CONTEXT,
    calculate_applyset_id,
    get_canonical_resource_kind_name,
)


def test__ApplySet__dump() -> None:
    applyset = ApplySet.new("test-applyset", "default")
    applyset.tooling = "kubectl/1.30"
    applyset.contains_group_kinds = ["Deployment.apps", "Service"]
    applyset.validate()

    assert applyset.dump() == {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "test-applyset",
            "namespace": "default",
            "annotations": {
                "applyset.kubernetes.io/tooling": "kubectl/1.30",
                "applyset.kubernetes.io/contains-group-kinds": "Deployment.apps,Service",
            },
            "labels": {
                "applyset.kubernetes.io/id": calculate_applyset_id(
                    name="test-applyset",
                    namespace="default",
                ),
            },
        },
    }


def test__ApplySet__dump_with_context() -> None:
    applyset = ApplySet.new("test-applyset", "default")
    applyset.tooling = "kubectl/1.30"
    applyset.contains_group_kinds = ["Deployment.apps", "Service"]
    applyset.context = ApplySetContext(
        source="cli",
        files=["test.yaml"],
    )
    applyset.validate()

    result = applyset.dump()
    assert result["metadata"]["annotations"][NYL_ANNOTATION_LAST_APPLIED_CONTEXT] == '{"source":"cli","files":["test.yaml"]}'


def test__ApplySet__dump_with_argocd_context() -> None:
    applyset = ApplySet.new("test-applyset", "default")
    applyset.tooling = "kubectl/1.30"
    applyset.contains_group_kinds = ["Deployment.apps", "Service"]
    applyset.context = ApplySetContext(
        source="argocd",
        files=["test.yaml"],
        revision="abc123",
        app_name="my-app",
    )
    applyset.validate()

    result = applyset.dump()
    assert result["metadata"]["annotations"][NYL_ANNOTATION_LAST_APPLIED_CONTEXT] == '{"source":"argocd","files":["test.yaml"],"revision":"abc123","app_name":"my-app"}'


def test__ApplySetContext__to_json() -> None:
    # Test CLI context
    context = ApplySetContext(source="cli", files=["a.yaml", "b.yaml"])
    assert context.to_json() == '{"source":"cli","files":["a.yaml","b.yaml"]}'

    # Test ArgoCD context with all fields
    context = ApplySetContext(
        source="argocd",
        files=["test.yaml"],
        revision="abc123def",
        app_name="my-app",
    )
    assert context.to_json() == '{"source":"argocd","files":["test.yaml"],"revision":"abc123def","app_name":"my-app"}'

    # Test minimal context
    context = ApplySetContext(source="cli")
    assert context.to_json() == '{"source":"cli"}'


def test__calculate_applyset_id() -> None:
    # Verify the ID format is correct for ConfigMap-based ApplySets
    applyset_id = calculate_applyset_id(name="test", namespace="default")
    assert applyset_id.startswith("applyset-")
    assert applyset_id.endswith("-v1")


def test__get_canonical_resource_kind_name() -> None:
    # The format is <Kind>.<group> - singular, capitalized Kind name
    assert get_canonical_resource_kind_name("v1", "Pod") == "Pod"
    assert get_canonical_resource_kind_name("apps/v1", "Deployment") == "Deployment.apps"
    assert get_canonical_resource_kind_name("nyl.io/v1", "ApplySet") == "ApplySet.nyl.io"
    assert get_canonical_resource_kind_name("argoproj.io/v1alpha1", "CronWorkflow") == "CronWorkflow.argoproj.io"
