"""Tests for ManifestLoaderService."""

import tempfile
from pathlib import Path

import pytest

from nyl.models.errors import ManifestValidationError
from nyl.services.manifest import ManifestLoaderService, ManifestsWithSource
from nyl.tools.types import Resource, ResourceList


@pytest.fixture
def temp_manifest_dir():
    """Create a temporary directory for test manifests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def service():
    """Create a ManifestLoaderService instance."""
    return ManifestLoaderService()


def test_load_manifests_single_file(temp_manifest_dir, service):
    """Test loading a single manifest file."""
    manifest_file = temp_manifest_dir / "deployment.yaml"
    manifest_file.write_text("""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
""")

    result = service.load_manifests([manifest_file])

    assert len(result) == 1
    assert result[0].file == manifest_file
    assert len(result[0].resources) == 1
    assert result[0].resources[0]["kind"] == "Deployment"
    assert result[0].resources[0]["metadata"]["name"] == "my-app"


def test_load_manifests_from_directory(temp_manifest_dir, service):
    """Test loading all manifests from a directory."""
    # Create multiple manifest files
    (temp_manifest_dir / "app1.yaml").write_text("""
apiVersion: v1
kind: Service
metadata:
  name: app1
""")
    (temp_manifest_dir / "app2.yaml").write_text("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: app2-config
""")

    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 2
    kinds = {r.resources[0]["kind"] for r in result}
    assert "Service" in kinds
    assert "ConfigMap" in kinds


def test_load_manifests_skips_nyl_prefixed_files(temp_manifest_dir, service):
    """Test that files starting with 'nyl-' are skipped."""
    (temp_manifest_dir / "app.yaml").write_text("""
apiVersion: v1
kind: Service
metadata:
  name: app
""")
    (temp_manifest_dir / "nyl-project.yaml").write_text("""
some: config
""")

    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 1
    assert result[0].file.name == "app.yaml"


def test_load_manifests_skips_hidden_files(temp_manifest_dir, service):
    """Test that hidden files (starting with '.') are skipped."""
    (temp_manifest_dir / "app.yaml").write_text("""
apiVersion: v1
kind: Service
metadata:
  name: app
""")
    (temp_manifest_dir / ".hidden.yaml").write_text("""
apiVersion: v1
kind: Secret
metadata:
  name: secret
""")

    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 1
    assert result[0].file.name == "app.yaml"


def test_load_manifests_skips_underscore_files(temp_manifest_dir, service):
    """Test that files starting with '_' are skipped."""
    (temp_manifest_dir / "app.yaml").write_text("""
apiVersion: v1
kind: Service
metadata:
  name: app
""")
    (temp_manifest_dir / "_template.yaml").write_text("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: template
""")

    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 1
    assert result[0].file.name == "app.yaml"


def test_load_manifests_only_loads_yaml_files(temp_manifest_dir, service):
    """Test that only .yaml files are loaded."""
    (temp_manifest_dir / "app.yaml").write_text("""
apiVersion: v1
kind: Service
metadata:
  name: app
""")
    (temp_manifest_dir / "readme.txt").write_text("This is a readme")
    (temp_manifest_dir / "config.json").write_text('{"key": "value"}')

    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 1
    assert result[0].file.name == "app.yaml"


def test_load_manifests_multiple_resources_in_file(temp_manifest_dir, service):
    """Test loading a file with multiple YAML documents."""
    manifest_file = temp_manifest_dir / "multi.yaml"
    manifest_file.write_text("""
apiVersion: v1
kind: Namespace
metadata:
  name: my-namespace
---
apiVersion: v1
kind: Service
metadata:
  name: my-service
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
""")

    result = service.load_manifests([manifest_file])

    assert len(result) == 1
    assert len(result[0].resources) == 3
    kinds = [r["kind"] for r in result[0].resources]
    assert kinds == ["Namespace", "Service", "Deployment"]


def test_load_manifests_empty_directory_returns_empty_list(temp_manifest_dir, service):
    """Test that loading from empty directory returns empty list."""
    result = service.load_manifests([temp_manifest_dir])

    assert len(result) == 0
    # Note: Warning is logged but we don't test it here since loguru doesn't integrate with caplog by default


def test_load_manifests_invalid_yaml_raises_error(temp_manifest_dir, service):
    """Test that invalid YAML raises ManifestValidationError."""
    manifest_file = temp_manifest_dir / "invalid.yaml"
    # Create truly invalid YAML with syntax errors
    manifest_file.write_text("""
apiVersion: v1
kind: Service
metadata: {
  name: invalid
  unclosed: bracket
}
bad syntax here [[[
""")

    with pytest.raises(ManifestValidationError) as exc_info:
        service.load_manifests([manifest_file])

    assert "Failed to load manifest" in str(exc_info.value)
    assert "invalid.yaml" in str(exc_info.value)


def test_extract_local_variables_basic(service):
    """Test extracting local variables from manifest."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"$var1": "value1", "$var2": "value2"}),
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    variables = service.extract_local_variables(source)

    assert variables == {"var1": "value1", "var2": "value2"}
    # Local variable resource should be removed
    assert len(source.resources) == 1
    assert source.resources[0]["kind"] == "Service"


def test_extract_local_variables_invalid_keys_raises_error(service):
    """Test that local variables with non-$ keys raise error."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"$valid": "value", "invalid": "key"})]),
        file=Path("test.yaml"),
    )

    with pytest.raises(ManifestValidationError) as exc_info:
        service.extract_local_variables(source)

    assert "don't start with '$'" in str(exc_info.value)
    assert "invalid" in str(exc_info.value)


def test_extract_local_variables_no_variables(service):
    """Test extracting when there are no local variables."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    variables = service.extract_local_variables(source)

    assert variables == {}
    assert len(source.resources) == 1


def test_extract_local_variables_multiple_definitions(service):
    """Test extracting multiple local variable definitions."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"$var1": "value1"}),
                Resource({"$var2": "value2", "$var3": "value3"}),
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
            ]
        ),
        file=Path("test.yaml"),
    )

    variables = service.extract_local_variables(source)

    assert variables == {"var1": "value1", "var2": "value2", "var3": "value3"}
    assert len(source.resources) == 1


def test_validate_manifest_structure_valid(service):
    """Test validation passes for valid manifests."""
    source = ManifestsWithSource(
        resources=ResourceList(
            [
                Resource({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}),
                Resource(
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "deploy"},
                    }
                ),
            ]
        ),
        file=Path("test.yaml"),
    )

    # Should not raise
    service.validate_manifest_structure(source)


def test_validate_manifest_structure_missing_api_version(service):
    """Test validation fails for missing apiVersion."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"kind": "Service", "metadata": {"name": "svc"}})]),
        file=Path("test.yaml"),
    )

    with pytest.raises(ManifestValidationError) as exc_info:
        service.validate_manifest_structure(source)

    assert "missing 'apiVersion' field" in str(exc_info.value)


def test_validate_manifest_structure_missing_kind(service):
    """Test validation fails for missing kind."""
    source = ManifestsWithSource(
        resources=ResourceList([Resource({"apiVersion": "v1", "metadata": {"name": "svc"}})]),
        file=Path("test.yaml"),
    )

    with pytest.raises(ManifestValidationError) as exc_info:
        service.validate_manifest_structure(source)

    assert "missing 'kind' field" in str(exc_info.value)


def test_discover_files_mixed_input(temp_manifest_dir, service):
    """Test file discovery with both files and directories."""
    # Create a subdirectory
    subdir = temp_manifest_dir / "subdir"
    subdir.mkdir()

    # Create files in main dir
    (temp_manifest_dir / "main.yaml").write_text("apiVersion: v1\nkind: Service")

    # Create files in subdir
    (subdir / "sub.yaml").write_text("apiVersion: v1\nkind: ConfigMap")

    # Explicitly pass both directory and file
    specific_file = temp_manifest_dir / "main.yaml"

    files = service._discover_files([temp_manifest_dir, specific_file])

    # Should get files from directory (including main.yaml) + explicitly specified file
    # Note: main.yaml will appear twice (once from dir scan, once explicit)
    file_names = [f.name for f in files]
    assert "main.yaml" in file_names
    # Subdir files should NOT be included (no recursion)
    assert "sub.yaml" not in file_names
