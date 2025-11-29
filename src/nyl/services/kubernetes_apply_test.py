"""Tests for KubernetesApplyService."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, call

import pytest

from nyl.models.errors import ApplySetError
from nyl.resources.applyset import ApplySet
from nyl.services.kubernetes_apply import KubernetesApplyService
from nyl.services.manifest import ManifestsWithSource
from nyl.tools.kubectl import Kubectl
from nyl.tools.types import Resource, ResourceList


@pytest.fixture
def mock_kubectl():
    """Create a mock Kubectl instance."""
    return Mock(spec=Kubectl)


@pytest.fixture
def service(mock_kubectl):
    """Create a KubernetesApplyService instance."""
    return KubernetesApplyService(kubectl=mock_kubectl, kube_version="1.30")


def test_find_or_create_applyset_no_applyset_no_autogen(service):
    """Test that None is returned when no ApplySet and auto_generate=False."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("test.yaml"),
    )

    result = service.find_or_create_applyset(source, namespace="default", auto_generate=False)

    assert result is None
    assert len(source.resources) == 1  # No resources removed


def test_find_or_create_applyset_finds_existing(service):
    """Test finding an existing ApplySet in resources."""
    applyset_resource = Resource(
        {
            "apiVersion": "nyl.io/v1",  # Correct API version
            "kind": "ApplySet",
            "metadata": {"name": "my-applyset"},  # ApplySets are cluster-scoped
        }
    )
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                applyset_resource,
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.find_or_create_applyset(source, namespace="default", auto_generate=False)

    assert result is not None
    assert isinstance(result, ApplySet)
    # ApplySet should be removed from resources
    assert len(source.resources) == 1
    assert source.resources[0]["kind"] == "Service"


def test_find_or_create_applyset_multiple_raises_error(service):
    """Test that multiple ApplySets raises an error."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {
                        "apiVersion": "nyl.io/v1",
                        "kind": "ApplySet",
                        "metadata": {"name": "applyset1"},
                    }
                ),
                Resource(
                    {
                        "apiVersion": "nyl.io/v1",
                        "kind": "ApplySet",
                        "metadata": {"name": "applyset2"},
                    }
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    with pytest.raises(ApplySetError) as exc_info:
        service.find_or_create_applyset(source, namespace="default", auto_generate=False)

    assert "Multiple ApplySet resources" in str(exc_info.value)
    # applyset_count is only set if present in details
    if "applyset_count" in exc_info.value.details:
        assert exc_info.value.details["applyset_count"] == 2


def test_find_or_create_applyset_autogenerate_success(service):
    """Test auto-generating an ApplySet."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("test.yaml"),
    )

    result = service.find_or_create_applyset(source, namespace="my-namespace", auto_generate=True)

    assert result is not None
    assert isinstance(result, ApplySet)
    assert result.metadata.name == "my-namespace"


def test_find_or_create_applyset_autogenerate_no_namespace_raises_error(service):
    """Test that auto-generate without namespace raises error."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("test.yaml"),
    )

    with pytest.raises(ApplySetError) as exc_info:
        service.find_or_create_applyset(source, namespace="", auto_generate=True)

    assert "No default namespace defined" in str(exc_info.value)


def test_prepare_applyset(service):
    """Test preparing an ApplySet for application."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}),
        ]
    )

    service.prepare_applyset(applyset, resources)

    # Should have set group kinds
    assert applyset.contains_group_kinds is not None
    assert len(applyset.contains_group_kinds) > 0
    # Should have set tooling
    assert applyset.tooling == "kubectl/v1.30"


def test_apply_with_applyset_applies_applyset_first(service, mock_kubectl):
    """Test that ApplySet is applied before resources."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.apply_with_applyset(resources, applyset, source_file="test.yaml", prune=False)

    # Should call apply twice: once for ApplySet, once for resources
    assert mock_kubectl.apply.call_count == 2

    # First call should be ApplySet with force_conflicts
    first_call = mock_kubectl.apply.call_args_list[0]
    assert first_call[1]["force_conflicts"] is True

    # Second call should be resources with applyset reference
    second_call = mock_kubectl.apply.call_args_list[1]
    assert second_call[1]["applyset"] == applyset.reference


def test_apply_with_applyset_without_applyset(service, mock_kubectl):
    """Test applying resources without an ApplySet."""
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.apply_with_applyset(resources, applyset=None, source_file="test.yaml")

    # Should call apply once for resources only
    assert mock_kubectl.apply.call_count == 1
    call_args = mock_kubectl.apply.call_args
    assert call_args[0][0] == resources


def test_apply_with_applyset_prune_enabled(service, mock_kubectl):
    """Test that prune flag is passed to kubectl."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.apply_with_applyset(resources, applyset, source_file="test.yaml", prune=True)

    # Second call should have prune=True
    second_call = mock_kubectl.apply.call_args_list[1]
    assert second_call[1]["prune"] is True


def test_diff_with_applyset_diffs_both(service, mock_kubectl):
    """Test that diff is called for both ApplySet and resources."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.diff_with_applyset(resources, applyset)

    # Should call diff twice
    assert mock_kubectl.diff.call_count == 2


def test_diff_with_applyset_without_applyset(service, mock_kubectl):
    """Test diff without an ApplySet."""
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.diff_with_applyset(resources, applyset=None)

    # Should call diff once for resources only
    assert mock_kubectl.diff.call_count == 1


def test_output_yaml_with_applyset(service, capsys):
    """Test YAML output includes ApplySet."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.output_yaml(resources, applyset)

    captured = capsys.readouterr()
    # Should have separator for ApplySet
    assert "---" in captured.out
    # Should contain ApplySet
    assert "ApplySet" in captured.out
    # Should contain Service
    assert "Service" in captured.out


def test_output_yaml_without_applyset(service, capsys):
    """Test YAML output without ApplySet."""
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.output_yaml(resources, applyset=None)

    captured = capsys.readouterr()
    # Should contain Service
    assert "Service" in captured.out
    # Should not contain ApplySet
    assert "ApplySet" not in captured.out


def test_tag_resources_with_applyset(service):
    """Test tagging resources with ApplySet labels."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}),
        ]
    )

    service.tag_resources_with_applyset(resources, applyset, applyset_part_of=True)

    # All resources should have the label
    for resource in resources:
        assert "labels" in resource["metadata"]
        assert "applyset.kubernetes.io/part-of" in resource["metadata"]["labels"]


def test_tag_resources_with_applyset_part_of_false(service):
    """Test that labels are not added when applyset_part_of=False."""
    applyset = ApplySet.new("test-applyset")
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    service.tag_resources_with_applyset(resources, applyset, applyset_part_of=False)

    # Resources should not have the label
    assert "labels" not in resources[0]["metadata"] or \
           "applyset.kubernetes.io/part-of" not in resources[0]["metadata"].get("labels", {})


def test_find_namespace_resources(service):
    """Test finding namespace resources."""
    resources = ResourceList(
        [
            Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns1"}}),
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns2"}}),
        ]
    )

    result = service.find_namespace_resources(resources)

    assert result == {"ns1", "ns2"}


def test_find_namespace_resources_empty(service):
    """Test finding namespaces when none exist."""
    resources = ResourceList(
        [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
    )

    result = service.find_namespace_resources(resources)

    assert result == set()
