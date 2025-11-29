"""Tests for NamespaceResolverService."""

from pathlib import Path

import pytest

from nyl.models.errors import NamespaceAmbiguityError
from nyl.services.manifest import ManifestsWithSource
from nyl.services.namespace import NamespaceResolverService
from nyl.tools.types import Resource, ResourceList


@pytest.fixture
def service():
    """Create a NamespaceResolverService instance."""
    return NamespaceResolverService()


def test_resolve_default_namespace_no_namespace_resource_uses_fallback(service):
    """Test that fallback is used when no Namespace resources exist."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback="my-fallback")

    assert result == "my-fallback"


def test_resolve_default_namespace_no_namespace_resource_uses_filename(service):
    """Test that filename stem is used when no Namespace and no fallback."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("my-application.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback=None)

    assert result == "my-application"


def test_resolve_default_namespace_strips_nyl_extension(service):
    """Test that .nyl suffix is stripped from filename."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]
        ),
        file=Path("my-app.nyl.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback=None)

    assert result == "my-app"


def test_resolve_default_namespace_single_namespace(service):
    """Test that single Namespace resource name is used."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "production"}}
                ),
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    assert result == "production"


def test_resolve_default_namespace_multiple_with_annotation(service):
    """Test that annotated namespace is used when multiple exist."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "staging"}}
                ),
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": "production",
                            "annotations": {"nyl.io/is-default-namespace": "true"},
                        },
                    }
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    assert result == "production"


def test_resolve_default_namespace_multiple_no_annotation_uses_alphabetical(service):
    """Test that first alphabetical namespace is used when multiple exist without annotation."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "zebra"}}
                ),
                Resource(
                    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "alpha"}}
                ),
                Resource(
                    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "beta"}}
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    assert result == "alpha"


def test_resolve_default_namespace_multiple_with_multiple_annotations_raises_error(service):
    """Test that error is raised when multiple namespaces have the default annotation."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": "ns1",
                            "annotations": {"nyl.io/is-default-namespace": "true"},
                        },
                    }
                ),
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": "ns2",
                            "annotations": {"nyl.io/is-default-namespace": "true"},
                        },
                    }
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    with pytest.raises(NamespaceAmbiguityError) as exc_info:
        service.resolve_default_namespace(source)

    error = exc_info.value
    assert "Multiple Namespace resources" in error.message
    assert "ns1" in str(error)
    assert "ns2" in str(error)
    assert error.details.get("namespaces_found") is not None


def test_find_namespace_resources_finds_all(service):
    """Test finding all Namespace resources in a list."""
    resources = ResourceList(
        [
            Resource(
                {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns1"}}
            ),
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource(
                {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns2"}}
            ),
            Resource(
                {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}
            ),
        ]
    )

    result = service.find_namespace_resources(resources)

    assert len(result) == 2
    assert result[0]["metadata"]["name"] == "ns1"
    assert result[1]["metadata"]["name"] == "ns2"


def test_find_namespace_resources_empty_list(service):
    """Test finding namespaces in empty list."""
    resources = ResourceList([])

    result = service.find_namespace_resources(resources)

    assert len(result) == 0


def test_find_namespace_resources_no_namespaces(service):
    """Test finding namespaces when none exist."""
    resources = ResourceList(
        [
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource(
                {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}
            ),
        ]
    )

    result = service.find_namespace_resources(resources)

    assert len(result) == 0


def test_is_namespace_resource_true_for_namespace(service):
    """Test that v1/Namespace is recognized."""
    resource = Resource(
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "test"}}
    )

    assert service._is_namespace_resource(resource)


def test_is_namespace_resource_false_for_other_kinds(service):
    """Test that non-Namespace resources are not recognized."""
    resources = [
        Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
        Resource(
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}
        ),
        Resource({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "cm"}}),
    ]

    for resource in resources:
        assert not service._is_namespace_resource(resource)


def test_is_namespace_resource_false_for_wrong_api_version(service):
    """Test that Namespace with wrong apiVersion is not recognized."""
    resource = Resource(
        {"apiVersion": "custom/v1", "kind": "Namespace", "metadata": {"name": "test"}}
    )

    assert not service._is_namespace_resource(resource)


def test_populate_namespaces_adds_namespace_to_resources(service):
    """Test that populate_namespaces adds namespace to resources without one."""
    resources = ResourceList(
        [
            Resource(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "svc"},
                    "spec": {},
                }
            ),
            Resource(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "deploy"},
                    "spec": {},
                }
            ),
        ]
    )

    service.populate_namespaces(resources, "my-namespace")

    assert resources[0]["metadata"]["namespace"] == "my-namespace"
    assert resources[1]["metadata"]["namespace"] == "my-namespace"


def test_populate_namespaces_preserves_existing_namespace(service):
    """Test that populate_namespaces doesn't override existing namespaces."""
    resources = ResourceList(
        [
            Resource(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "svc", "namespace": "existing"},
                    "spec": {},
                }
            ),
            Resource(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "deploy"},
                    "spec": {},
                }
            ),
        ]
    )

    service.populate_namespaces(resources, "my-namespace")

    # First resource keeps its namespace
    assert resources[0]["metadata"]["namespace"] == "existing"
    # Second resource gets the default
    assert resources[1]["metadata"]["namespace"] == "my-namespace"


def test_resolve_with_annotation_value_false_not_treated_as_default(service):
    """Test that annotation with 'false' value doesn't mark namespace as default."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": "ns1",
                            "annotations": {"nyl.io/is-default-namespace": "false"},
                        },
                    }
                ),
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": "ns2",
                            "annotations": {"nyl.io/is-default-namespace": "true"},
                        },
                    }
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    # Should pick ns2 (the one with "true")
    assert result == "ns2"
