import os
from unittest.mock import patch

from nyl.resources.applyset import (
    APPLYSET_LABEL_PART_OF,
    ApplySet,
    ApplySetContext,
    ApplySetManager,
    NYL_ANNOTATION_LAST_APPLIED_CONTEXT,
    calculate_applyset_id,
    get_canonical_resource_kind_name,
)
from nyl.tools.types import Resource, ResourceList


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
        source_path="/apps/myapp",
        source_repo_url="https://github.com/example/repo",
        target_revision="main",
    )
    applyset.validate()

    result = applyset.dump()
    expected = '{"source":"argocd","files":["test.yaml"],"revision":"abc123","app_name":"my-app","source_path":"/apps/myapp","source_repo_url":"https://github.com/example/repo","target_revision":"main"}'
    assert result["metadata"]["annotations"][NYL_ANNOTATION_LAST_APPLIED_CONTEXT] == expected


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
        source_path="/apps/myapp",
        source_repo_url="https://github.com/example/repo",
        target_revision="main",
    )
    expected = '{"source":"argocd","files":["test.yaml"],"revision":"abc123def","app_name":"my-app","source_path":"/apps/myapp","source_repo_url":"https://github.com/example/repo","target_revision":"main"}'
    assert context.to_json() == expected

    # Test minimal context
    context = ApplySetContext(source="cli")
    assert context.to_json() == '{"source":"cli"}'


def test__ApplySetContext__from_environment_cli() -> None:
    # Test CLI context (no ArgoCD env vars)
    with patch.dict(os.environ, {}, clear=True):
        context = ApplySetContext.from_environment(files=["test.yaml"])
        assert context.source == "cli"
        assert context.files == ["test.yaml"]
        assert context.app_name is None
        assert context.revision is None


def test__ApplySetContext__from_environment_argocd() -> None:
    # Test ArgoCD context (with ArgoCD env vars)
    argocd_env = {
        "ARGOCD_APP_NAME": "my-app",
        "ARGOCD_APP_REVISION": "abc123",
        "ARGOCD_APP_SOURCE_PATH": "/apps/myapp",
        "ARGOCD_APP_SOURCE_REPO_URL": "https://github.com/example/repo",
        "ARGOCD_APP_SOURCE_TARGET_REVISION": "main",
    }
    with patch.dict(os.environ, argocd_env, clear=True):
        context = ApplySetContext.from_environment(files=["test.yaml"])
        assert context.source == "argocd"
        assert context.files == ["test.yaml"]
        assert context.app_name == "my-app"
        assert context.revision == "abc123"
        assert context.source_path == "/apps/myapp"
        assert context.source_repo_url == "https://github.com/example/repo"
        assert context.target_revision == "main"


def test__ApplySetManager__disabled() -> None:
    # Test that manager passes through resources when disabled
    manager = ApplySetManager(applyset=None)
    assert not manager.enabled

    resources = ResourceList([
        Resource({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}})
    ])
    result = manager.prepare_resources(resources)
    assert len(result) == 1
    assert result[0]["kind"] == "Pod"


def test__ApplySetManager__prepare_resources() -> None:
    # Test that manager adds ConfigMap and part-of labels
    applyset = ApplySet.new("test-applyset", "default")
    applyset.tooling = "kubectl/1.30"
    applyset.contains_group_kinds = ["Pod"]

    manager = ApplySetManager(applyset=applyset, add_part_of_labels=True)
    assert manager.enabled

    resources = ResourceList([
        Resource({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}})
    ])
    result = manager.prepare_resources(resources)

    # Should have ConfigMap at the beginning + original resource
    assert len(result) == 2
    assert result[0]["kind"] == "ConfigMap"
    assert result[0]["metadata"]["name"] == "test-applyset"
    assert result[1]["kind"] == "Pod"
    assert result[1]["metadata"]["labels"][APPLYSET_LABEL_PART_OF] == applyset.id


def test__ApplySetManager__prepare_resources_no_labels() -> None:
    # Test that manager doesn't add part-of labels when disabled
    applyset = ApplySet.new("test-applyset", "default")
    applyset.tooling = "kubectl/1.30"
    applyset.contains_group_kinds = ["Pod"]

    manager = ApplySetManager(applyset=applyset, add_part_of_labels=False)

    resources = ResourceList([
        Resource({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}})
    ])
    result = manager.prepare_resources(resources)

    # Should have ConfigMap but no part-of label on the Pod
    assert len(result) == 2
    assert result[0]["kind"] == "ConfigMap"
    assert APPLYSET_LABEL_PART_OF not in result[1]["metadata"].get("labels", {})


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
