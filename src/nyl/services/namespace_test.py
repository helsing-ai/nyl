"""Tests for NamespaceResolverService."""

from pathlib import Path

import pytest

from nyl.models.errors import NamespaceAmbiguityError
from nyl.services.manifest import ManifestsWithSource
from nyl.services.namespace import NamespaceResolverService
from nyl.tools.types import Resource, ResourceList


@pytest.fixture
def service() -> NamespaceResolverService:
    """Create a NamespaceResolverService instance."""
    return NamespaceResolverService()


def test_resolve_default_namespace_no_namespace_resource_uses_fallback(service: NamespaceResolverService) -> None:
    """Test that fallback is used when no Namespace resources exist."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback="my-fallback")

    assert result == "my-fallback"


def test_resolve_default_namespace_no_namespace_resource_uses_filename(service: NamespaceResolverService) -> None:
    """Test that filename stem is used when no Namespace and no fallback."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]),
        file=Path("my-application.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback=None)

    assert result == "my-application"


def test_resolve_default_namespace_strips_nyl_extension(service: NamespaceResolverService) -> None:
    """Test that .nyl suffix is stripped from filename."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}})]),
        file=Path("my-app.nyl.yaml"),
    )

    result = service.resolve_default_namespace(source, fallback=None)

    assert result == "my-app"


def test_resolve_default_namespace_single_namespace(service: NamespaceResolverService) -> None:
    """Test that single Namespace resource name is used."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "production"}}),
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    assert result == "production"


def test_resolve_default_namespace_multiple_with_annotation(service: NamespaceResolverService) -> None:
    """Test that annotated namespace is used when multiple exist."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "staging"}}),
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


def test_resolve_default_namespace_multiple_no_annotation_uses_alphabetical(service: NamespaceResolverService) -> None:
    """Test that first alphabetical namespace is used when multiple exist without annotation."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "zebra"}}),
                Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "alpha"}}),
                Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "beta"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    result = service.resolve_default_namespace(source)

    assert result == "alpha"


def test_resolve_default_namespace_multiple_with_multiple_annotations_raises_error(
    service: NamespaceResolverService,
) -> None:
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


def test_find_namespace_resources_finds_all(service: NamespaceResolverService) -> None:
    """Test finding all Namespace resources in a list."""
    resources = ResourceList(
        [
            Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns1"}}),
            Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns2"}}),
            Resource({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "deploy"}}),
        ]
    )

    result = service.find_namespace_resources(resources)

    assert len(result) == 2
    assert result[0]["metadata"]["name"] == "ns1"
    assert result[1]["metadata"]["name"] == "ns2"


def test_populate_namespaces_adds_namespace_to_resources(service: NamespaceResolverService) -> None:
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


def test_populate_namespaces_preserves_existing_namespace(service: NamespaceResolverService) -> None:
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


def test_resolve_with_annotation_value_false_not_treated_as_default(service: NamespaceResolverService) -> None:
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
