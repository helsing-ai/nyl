# tests/commands/test_template.py
import pytest
from unittest.mock import patch, MagicMock, ANY # Added ANY
from typer.testing import CliRunner
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any as TypingAny # Renamed Any to TypingAny to avoid conflict

from nyl.main import app # Assuming app is in nyl.main, adjust if it's in nyl.commands.app
from nyl.core.templating_processor import OnLookupFailure # For type checking CLI option
from nyl.resources.applyset import ApplySet
from nyl.tools.types import Resource, ResourceList

# Sample resource for testing output
SAMPLE_RESOURCE_DICT: Dict[str, TypingAny] = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": "test-cm"},
    "data": {"foo": "bar"},
}

# --- Fixtures ---

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()

# --- Tests ---

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_basic_invocation(
    mock_kubectl_class: MagicMock, 
    mock_process_templates: MagicMock, 
    runner: CliRunner,
    tmp_path: Path
):
    """Test basic `nyl template` invocation."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("kind: Dummy")

    # Configure mock_process_templates to return a simple result
    mock_process_templates.return_value = [
        (manifest_file, ResourceList([SAMPLE_RESOURCE_DICT]), None)
    ]

    result = runner.invoke(app, ["template", str(manifest_file)])

    assert result.exit_code == 0
    mock_process_templates.assert_called_once()
    
    # Check some key args passed to process_templates
    args, kwargs = mock_process_templates.call_args
    assert kwargs['paths'] == [manifest_file]
    assert kwargs['profile_name'] is None
    assert kwargs['secrets_provider_name'] == "default" 
    # ... add more assertions for default values of other args if necessary

    # Check stdout for YAML output
    assert "kind: ConfigMap" in result.stdout
    assert "name: test-cm" in result.stdout
    assert "foo: bar" in result.stdout

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_apply_option(
    mock_kubectl_class: MagicMock, 
    mock_process_templates: MagicMock, 
    runner: CliRunner,
    tmp_path: Path
):
    """Test `nyl template --apply`."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("kind: DummyApply")
    
    mock_kubectl_instance = mock_kubectl_class.return_value
    mock_process_templates.return_value = [
        (manifest_file, ResourceList([SAMPLE_RESOURCE_DICT]), None)
    ]

    result = runner.invoke(app, ["template", str(manifest_file), "--apply"])

    assert result.exit_code == 0
    mock_process_templates.assert_called_once()
    mock_kubectl_instance.apply.assert_called_once_with(
        manifests=ResourceList([SAMPLE_RESOURCE_DICT]),
        applyset=None,
        prune=False, # Default when no applyset
        force_conflicts=True
    )

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_diff_option(
    mock_kubectl_class: MagicMock, 
    mock_process_templates: MagicMock, 
    runner: CliRunner,
    tmp_path: Path
):
    """Test `nyl template --diff`."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("kind: DummyDiff")

    mock_kubectl_instance = mock_kubectl_class.return_value
    mock_process_templates.return_value = [
        (manifest_file, ResourceList([SAMPLE_RESOURCE_DICT]), None)
    ]

    result = runner.invoke(app, ["template", str(manifest_file), "--diff"])

    assert result.exit_code == 0
    mock_process_templates.assert_called_once()
    mock_kubectl_instance.diff.assert_called_once_with(
        manifests=ResourceList([SAMPLE_RESOURCE_DICT]),
        applyset=None
    )

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_cli_options_passthrough(
    mock_kubectl_class: MagicMock,
    mock_process_templates: MagicMock,
    runner: CliRunner,
    tmp_path: Path
):
    """Test various CLI options are passed correctly to process_templates."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("kind: DummyOptions")

    mock_process_templates.return_value = [] # Return empty for simplicity

    runner.invoke(app, [
        "template", str(manifest_file),
        "--profile", "myprof",
        "--secrets", "mysecrets",
        "--default-namespace", "my-ns",
        "--on-lookup-failure", "SkipResource",
        "--jobs", "5",
        "--no-inline" # Test boolean flag
    ])
    
    mock_process_templates.assert_called_once()
    args, kwargs = mock_process_templates.call_args
    assert kwargs['profile_name'] == "myprof"
    assert kwargs['secrets_provider_name'] == "mysecrets"
    assert kwargs['default_namespace'] == "my-ns"
    assert kwargs['on_lookup_failure_config'] == OnLookupFailure.SkipResource.to_literal()
    assert kwargs['jobs'] == 5
    assert kwargs['inline_enabled'] is False

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_error_from_core(
    mock_kubectl_class: MagicMock,
    mock_process_templates: MagicMock,
    runner: CliRunner,
    tmp_path: Path
):
    """Test error handling when process_templates raises an exception."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("kind: DummyError")

    mock_process_templates.side_effect = ValueError("Core processing failed!")

    result = runner.invoke(app, ["template", str(manifest_file)])

    assert result.exit_code != 0 # Should be non-zero
    assert "Error processing templates: Core processing failed!" in result.stdout # Or stderr depending on Typer

@patch('nyl.commands.template.process_templates')
@patch('nyl.commands.template.Kubectl')
def test_template_apply_with_applyset(
    mock_kubectl_class: MagicMock,
    mock_process_templates: MagicMock,
    runner: CliRunner,
    tmp_path: Path
):
    """Test `nyl template --apply` with an ApplySet object returned."""
    manifest_file = tmp_path / "manifest_as.yaml"
    manifest_file.write_text("kind: DummyApplySet")

    mock_kubectl_instance = mock_kubectl_class.return_value
    
    # Mock ApplySet object
    mock_applyset = MagicMock(spec=ApplySet)
    mock_applyset.reference = "applyset-ref"
    mock_applyset.dump.return_value = {"kind": "ApplySet", "name": "test-as"}


    mock_process_templates.return_value = [
        (manifest_file, ResourceList([SAMPLE_RESOURCE_DICT]), mock_applyset)
    ]

    result = runner.invoke(app, ["template", str(manifest_file), "--apply"])
    assert result.exit_code == 0

    # Check apply calls: first for ApplySet, then for resources with applyset reference
    assert mock_kubectl_instance.apply.call_count == 2
    
    # Call for ApplySet object itself
    mock_kubectl_instance.apply.assert_any_call(
        ResourceList([{"kind": "ApplySet", "name": "test-as"}]),
        force_conflicts=True
    )
    
    # Call for the main resources
    mock_kubectl_instance.apply.assert_any_call(
        manifests=ResourceList([SAMPLE_RESOURCE_DICT]),
        applyset="applyset-ref",
        prune=True, # Prune is True when applyset is present
        force_conflicts=True
    )

# TODO: More tests
# - Test --no-applyset-part-of
# - Test ARGOCD_ENV_NYL_PROFILE and ARGOCD_ENV_NYL_CMP_TEMPLATE_INPUT environment variables
# - Test state_dir and cache_dir resolution (though this is more about setup than core call)
# - Test in_cluster option
# - Test generate_applysets override option
# - Test multiple input paths
# - Test what happens if a profile is requested but ProfileManager is not configured (edge case)
# - Test if metrics logging is called (might require patching time.perf_counter and json.dumps)
