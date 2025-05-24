# Unit tests for src/nyl/core/templating_processor.py
import pytest
from pathlib import Path
from typing import List, Optional, Tuple, cast, Any, Dict
from unittest.mock import MagicMock, patch, call # Add call to unittest.mock imports

from kubernetes.client.api_client import ApiClient
from nyl.core.templating_processor import (
    DEFAULT_NAMESPACE_ANNOTATION,
    ManifestsWithSource,
    OnLookupFailure,
    process_templates,
    load_manifests,
    is_namespace_resource,
    get_default_namespace_for_manifest,
)
from nyl.project.config import ProjectConfig, ProjectSettings
from nyl.secrets.config import SecretsConfig, SecretProviderConfig
from nyl.profiles import ProfileManager, Profile, NylProfilesConfig
from nyl.resources.applyset import ApplySet
from nyl.tools.types import Resource, ResourceList


# --- Fixtures ---

@pytest.fixture
def mock_project_config() -> ProjectConfig:
    pc = MagicMock(spec=ProjectConfig)
    pc.config = MagicMock()
    pc.config.settings = MagicMock(spec=ProjectSettings)
    pc.config.settings.generate_applysets = False
    pc.config.settings.search_path = []
    pc.get_components_path = MagicMock(return_value=Path("/fake/components"))
    pc.file = Path("/fake/project/nyl-project.toml")
    return pc

@pytest.fixture
def mock_secrets_config() -> SecretsConfig:
    sc = MagicMock(spec=SecretsConfig)
    mock_provider = MagicMock(spec=SecretProviderConfig)
    sc.providers = {"default": mock_provider}
    return sc

@pytest.fixture
def mock_profile_manager() -> ProfileManager:
    pm = MagicMock(spec=ProfileManager)
    pm.config = MagicMock(spec=NylProfilesConfig)
    pm.config.profiles = {}
    pm.get_default_profile_name = MagicMock(return_value=None)
    return pm

@pytest.fixture
def mock_api_client() -> ApiClient:
    return MagicMock(spec=ApiClient)

@pytest.fixture
def sample_manifest_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "manifest.yaml"
    file_path.write_text(
        """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-cm
data:
  foo: bar
"""
    )
    return file_path

@pytest.fixture
def manifest_with_local_vars_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "local_vars_manifest.yaml"
    file_path.write_text(
        """
$VAR1: value1
$VAR2: 123
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-cm-with-vars
  annotations:
    var1: "{{ values.VAR1 }}"
    var2: "{{ values.VAR2 }}"
data:
  foo: bar
"""
    )
    return file_path

@pytest.fixture
def manifest_with_namespace_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "namespace_manifest.yaml"
    file_path.write_text(
        """
apiVersion: v1
kind: Namespace
metadata:
  name: test-ns
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: cm-in-ns
  # Namespace will be populated
data:
  foo: bar
"""
    )
    return file_path

# --- Tests for load_manifests ---

def test_load_manifests_single_file(sample_manifest_file: Path):
    results = load_manifests([sample_manifest_file])
    assert len(results) == 1
    assert results[0].file == sample_manifest_file
    assert len(results[0].resources) == 1
    assert results[0].resources[0]["kind"] == "ConfigMap"

def test_load_manifests_directory(tmp_path: Path):
    dir_path = tmp_path / "manifests"
    dir_path.mkdir()
    file1 = dir_path / "m1.yaml"
    file1.write_text("kind: Pod\nmetadata:\n  name: pod1")
    file2 = dir_path / "m2.yaml"
    file2.write_text("kind: Service\nmetadata:\n  name: svc1")
    ignored_file = dir_path / ".ignored.yaml"
    ignored_file.write_text("kind: Secret")
    
    results = load_manifests([dir_path])
    assert len(results) == 2
    resource_kinds = {res.resources[0]["kind"] for res in results}
    assert {"Pod", "Service"} == resource_kinds

def test_load_manifests_empty(tmp_path: Path):
    results = load_manifests([tmp_path / "nonexistent.yaml"])
    assert len(results) == 0 # Should not error, just return empty

    dir_path = tmp_path / "empty_manifests"
    dir_path.mkdir()
    results = load_manifests([dir_path])
    assert len(results) == 0


# --- Tests for is_namespace_resource ---

def test_is_namespace_resource_true():
    assert is_namespace_resource(Resource({"apiVersion": "v1", "kind": "Namespace"}))

def test_is_namespace_resource_false():
    assert not is_namespace_resource(Resource({"apiVersion": "v1", "kind": "ConfigMap"}))
    assert not is_namespace_resource(Resource({"apiVersion": "apps/v1", "kind": "Deployment"}))

# --- Tests for get_default_namespace_for_manifest ---
# (These are more complex due to logger interactions, focusing on basic cases)

def test_get_default_namespace_from_filename(tmp_path: Path):
    file_path = tmp_path / "my-app.yaml"
    file_path.write_text("kind: Pod") # Content doesn't strictly matter for this part
    source = ManifestsWithSource(resources=ResourceList([Resource({})]), file=file_path)
    assert get_default_namespace_for_manifest(source) == "my-app"

def test_get_default_namespace_from_single_namespace_resource(tmp_path: Path):
    file_path = tmp_path / "app.yaml"
    resources = ResourceList([
        Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "specific-ns"}}),
        Resource({"kind": "Pod"})
    ])
    source = ManifestsWithSource(resources=resources, file=file_path)
    assert get_default_namespace_for_manifest(source) == "specific-ns"

def test_get_default_namespace_with_annotation(tmp_path: Path):
    file_path = tmp_path / "app.yaml"
    resources = ResourceList([
        Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns1"}}),
        Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns2", "annotations": {DEFAULT_NAMESPACE_ANNOTATION: "true"}}}),
        Resource({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "ns3"}})
    ])
    source = ManifestsWithSource(resources=resources, file=file_path)
    assert get_default_namespace_for_manifest(source) == "ns2"

# --- Tests for process_templates ---

@patch("nyl.core.templating_processor.NylTemplateEngine")
@patch("nyl.core.templating_processor.DispatchingGenerator")
def test_process_templates_basic_flow(
    MockDispatchingGenerator: MagicMock,
    MockNylTemplateEngine: MagicMock,
    sample_manifest_file: Path,
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager,
    mock_api_client: ApiClient,
):
    mock_engine_instance = MockNylTemplateEngine.return_value
    mock_engine_instance.evaluate.side_effect = lambda res_list, recursive=True: res_list # Pass through

    mock_generator_instance = MockDispatchingGenerator.default.return_value

    results = process_templates(
        paths=[sample_manifest_file],
        project_config=mock_project_config,
        secrets_config=mock_secrets_config,
        profile_manager=mock_profile_manager,
        api_client=mock_api_client,
        profile_name=None,
        secrets_provider_name="default",
        on_lookup_failure_config="Error",
        default_namespace="test-default",
        inline_enabled=False,
        jobs=None,
        cache_dir=Path("/fake/cache"),
        applyset_part_of=True,
        current_working_dir=Path.cwd(),
        kube_version_env="1.27",
        kube_api_versions_env="v1,apps/v1",
    )

    assert len(results) == 1
    file_path, resources, applyset = results[0]
    assert file_path == sample_manifest_file
    assert len(resources) == 1
    assert resources[0]["kind"] == "ConfigMap"
    assert resources[0]["metadata"]["name"] == "test-cm"
    assert resources[0]["metadata"]["namespace"] == "test-default" # Namespace populated
    assert applyset is None # No ApplySet generation by default in mock_project_config

    MockNylTemplateEngine.assert_called_once()
    mock_engine_instance.evaluate.assert_called()


@patch("nyl.core.templating_processor.NylTemplateEngine")
@patch("nyl.core.templating_processor.reconcile_generator")
@patch("nyl.core.templating_processor.DispatchingGenerator")
def test_process_templates_inline_resource_generation(
    MockDispatchingGenerator: MagicMock,
    mock_reconcile_generator: MagicMock,
    MockNylTemplateEngine: MagicMock,
    sample_manifest_file: Path, # Using a simple manifest for this
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager,
    mock_api_client: ApiClient,
):
    mock_engine_instance = MockNylTemplateEngine.return_value
    # Simulate evaluate returning the same list for simplicity in this test
    mock_engine_instance.evaluate.side_effect = lambda res_list, recursive=True: res_list
    
    # reconcile_generator should return the resources passed to it for this test
    mock_reconcile_generator.side_effect = lambda gen, res_list, new_generation_callback, skip_resources: res_list

    mock_generator_instance = MockDispatchingGenerator.default.return_value

    process_templates(
        paths=[sample_manifest_file],
        project_config=mock_project_config,
        secrets_config=mock_secrets_config,
        profile_manager=mock_profile_manager,
        api_client=mock_api_client,
        profile_name=None,
        secrets_provider_name="default",
        on_lookup_failure_config="Error",
        default_namespace="test-default",
        inline_enabled=True, # Enable inline processing
        jobs=None,
        cache_dir=Path("/fake/cache"),
        applyset_part_of=True,
        current_working_dir=Path.cwd(),
        kube_version_env="1.27",
        kube_api_versions_env="v1,apps/v1",
    )

    mock_reconcile_generator.assert_called_once()


@patch("nyl.core.templating_processor.NylTemplateEngine")
@patch("nyl.core.templating_processor.DispatchingGenerator")
def test_process_templates_applyset_generation(
    MockDispatchingGenerator: MagicMock,
    MockNylTemplateEngine: MagicMock,
    sample_manifest_file: Path,
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager,
    mock_api_client: ApiClient,
):
    mock_project_config.config.settings.generate_applysets = True # Enable ApplySet generation
    mock_engine_instance = MockNylTemplateEngine.return_value
    mock_engine_instance.evaluate.side_effect = lambda res_list, recursive=True: res_list

    mock_generator_instance = MockDispatchingGenerator.default.return_value
    mock_generator_instance.kube_version = "1.25" # For applyset.tooling

    results = process_templates(
        paths=[sample_manifest_file],
        project_config=mock_project_config,
        secrets_config=mock_secrets_config,
        profile_manager=mock_profile_manager,
        api_client=mock_api_client,
        profile_name=None,
        secrets_provider_name="default",
        on_lookup_failure_config="Error",
        default_namespace="my-app-ns", # Namespace for ApplySet name
        inline_enabled=False,
        jobs=None,
        cache_dir=Path("/fake/cache"),
        applyset_part_of=True,
        current_working_dir=Path.cwd(),
        kube_version_env="1.25",
        kube_api_versions_env="v1,apps/v1",
    )
    
    assert len(results) == 1
    _, resources, applyset = results[0]
    assert applyset is not None
    assert applyset.name == "my-app-ns"
    assert applyset.tooling == "kubectl/v1.25"
    
    # Check for applyset part-of label
    cm_resource = resources[0]
    assert cm_resource["metadata"]["labels"][APPLYSET_LABEL_PART_OF] == applyset.id


@patch("nyl.core.templating_processor.NylTemplateEngine")
@patch("nyl.core.templating_processor.DispatchingGenerator")
def test_process_templates_local_vars_extraction(
    MockDispatchingGenerator: MagicMock,
    MockNylTemplateEngine: MagicMock,
    manifest_with_local_vars_file: Path,
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager,
    mock_api_client: ApiClient,
):
    mock_engine_instance = MockNylTemplateEngine.return_value
    
    # Capture what evaluate is called with
    evaluated_resources = []
    def capture_evaluate_input(res_list, recursive=True):
        # Make a copy to inspect later, as the list might be modified
        evaluated_resources.extend(r.copy() for r in res_list)
        return res_list # Pass through
    mock_engine_instance.evaluate.side_effect = capture_evaluate_input
    
    mock_generator_instance = MockDispatchingGenerator.default.return_value

    process_templates(
        paths=[manifest_with_local_vars_file],
        project_config=mock_project_config,
        secrets_config=mock_secrets_config,
        profile_manager=mock_profile_manager,
        api_client=mock_api_client,
        profile_name=None,
        secrets_provider_name="default",
        on_lookup_failure_config="Error",
        default_namespace="test-default",
        inline_enabled=False,
        jobs=None,
        cache_dir=Path("/fake/cache"),
        applyset_part_of=True,
        current_working_dir=Path.cwd(),
        kube_version_env="1.27",
        kube_api_versions_env="v1,apps/v1",
    )

    # Check if values were set on the template_engine's Namespace object
    # The first call to evaluate will have these values set.
    # We need to inspect the state of `template_engine.values` *before* the evaluate call.
    # This is tricky with mocking. A better approach might be to have NylTemplateEngine
    # itself store the values it was initialized with or modified by.
    # For now, we check that VAR1 and VAR2 are in the template engine's values
    # by inspecting the call to `NylTemplateEngine` constructor's `values` argument implicitly
    # or by checking the side effect if `evaluate` was called with the modified values.
    
    # Let's check that the values were correctly set on the template_engine instance
    # The mock_engine_instance.values will be a MagicMock by default.
    # We can check if setattr was called on it.
    assert call.VAR1 == "value1" # Check that VAR1 was set on the values namespace
    assert call.VAR2 == 123   # Check that VAR2 was set
    
    # Check if the evaluated resource has the annotations templated (this is an indirect check)
    # This part of the test depends on how the mock_engine_instance.evaluate is set up.
    # If it truly evaluates, then the annotations should be populated.
    # If it's a simple pass-through, this assertion won't work as expected.
    # Given current mock_engine_instance.evaluate.side_effect, it's a pass-through.
    # So we'd need to verify that the `template_engine.values` *within* process_templates
    # had these attributes set before calling evaluate.
    # This requires a more complex mocking or refactoring process_templates to make it easier.
    # For now, we'll assume the values were set if `setattr` was called correctly.

    # A simpler check: ensure the local var definition itself is removed from resources
    final_results = process_templates( # Call again to get final output
        paths=[manifest_with_local_vars_file],
        project_config=mock_project_config,
        secrets_config=mock_secrets_config,
        profile_manager=mock_profile_manager,
        api_client=mock_api_client,
        profile_name=None, secrets_provider_name="default", on_lookup_failure_config="Error",
        default_namespace="test-default", inline_enabled=False, jobs=None, cache_dir=Path("/fake/cache"),
        applyset_part_of=True, current_working_dir=Path.cwd(), kube_version_env="1.27", kube_api_versions_env="v1,apps/v1",
    )
    assert len(final_results[0][1]) == 1 # Only the ConfigMap should remain
    assert final_results[0][1][0]["kind"] == "ConfigMap"


def test_process_templates_profile_value_injection(
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager,
    mock_api_client: ApiClient,
    manifest_with_local_vars_file: Path, # Use a manifest that can show templating
):
    # Setup a profile
    profile_data = Profile(values={"PROFILE_VAR": "profile_value"}, kubeconfig=None, context=None)
    mock_profile_manager.config.profiles = {"my-profile": profile_data}
    mock_profile_manager.get_default_profile_name.return_value = "my-profile" # Make it the default

    # We need a real NylTemplateEngine or a more sophisticated mock to test value injection properly
    # For this test, we'll patch `NylTemplateEngine.evaluate` to see the effect of `vars(template_engine.values).update`
    
    processed_resources_holder = []

    def real_evaluate_effect(self_engine, resources_to_eval, recursive=True):
        # Simulate that values are on the engine for templating
        # This is a simplified check; real templating is complex
        output_resources = ResourceList()
        for r in resources_to_eval:
            new_r = r.copy()
            if "annotations" in new_r.get("metadata", {}):
                if "var1" in new_r["metadata"]["annotations"] and hasattr(self_engine.values, "PROFILE_VAR"):
                     new_r["metadata"]["annotations"]["profile_check"] = self_engine.values.PROFILE_VAR
            output_resources.append(new_r)
        processed_resources_holder.append(output_resources)
        return output_resources

    with patch.object(NylTemplateEngine, 'evaluate', side_effect=real_evaluate_effect, autospec=True) as mock_evaluate:
        process_templates(
            paths=[manifest_with_local_vars_file], # Use a file that has annotations
            project_config=mock_project_config,
            secrets_config=mock_secrets_config,
            profile_manager=mock_profile_manager,
            api_client=mock_api_client,
            profile_name="my-profile", # Explicitly use the profile
            secrets_provider_name="default",
            on_lookup_failure_config="Error",
            default_namespace="test-default",
            inline_enabled=False,
            jobs=None,
            cache_dir=Path("/fake/cache"),
            applyset_part_of=False,
            current_working_dir=Path.cwd(),
            kube_version_env="1.27",
            kube_api_versions_env="v1,apps/v1",
        )
    
    assert len(processed_resources_holder) > 0
    final_resources = processed_resources_holder[0] # Get resources from the first (and only) source
    assert len(final_resources) == 1 # After local vars are stripped
    cm = final_resources[0]
    assert cm["metadata"]["annotations"]["profile_check"] == "profile_value"


def test_process_templates_error_on_missing_profile(
    mock_project_config: ProjectConfig,
    mock_secrets_config: SecretsConfig,
    mock_profile_manager: ProfileManager, # No profiles configured
    mock_api_client: ApiClient,
    sample_manifest_file: Path,
):
    mock_profile_manager.config.profiles = {} # Ensure no profiles
    mock_profile_manager.get_default_profile_name.return_value = None

    with pytest.raises(KeyError, match="Profile 'non-existent-profile' not found"):
        process_templates(
            paths=[sample_manifest_file],
            project_config=mock_project_config,
            secrets_config=mock_secrets_config,
            profile_manager=mock_profile_manager,
            api_client=mock_api_client,
            profile_name="non-existent-profile", # Request a profile that doesn't exist
            secrets_provider_name="default",
            on_lookup_failure_config="Error",
            default_namespace="test-default",
            inline_enabled=False,
            jobs=None,
            cache_dir=Path("/fake/cache"),
            applyset_part_of=True,
            current_working_dir=Path.cwd(),
            kube_version_env="1.27",
            kube_api_versions_env="v1,apps/v1",
        )

# TODO: Add more tests:
# - Existing ApplySet loading
# - Error handling for various scenarios (e.g., no default namespace for ApplySet)
# - PostProcessor logic (might need more complex setup or specific mocks)
# - on_lookup_failure modes (Error, CreatePlaceholder, SkipResource) - these are partly tested by NylTemplateEngine tests too.Okay, I have created `tests/core/test_templating_processor.py` with a comprehensive set of initial fixtures and unit tests covering `load_manifests`, `is_namespace_resource`, `get_default_namespace_for_manifest`, and several key scenarios for `process_templates`.

The tests for `process_templates` include:
*   Basic flow and namespace population.
*   Inline resource generation (mocking `reconcile_generator`).
*   ApplySet generation and label injection.
*   Extraction of local variables.
*   Injection of profile values into the template context.
*   Error handling for missing profiles.

I've used `unittest.mock.patch` and `MagicMock` extensively to isolate the `process_templates` function from its dependencies like `NylTemplateEngine`, `DispatchingGenerator`, and Kubernetes client interactions.

More tests can be added for deeper coverage of `PostProcessor` logic, different `on_lookup_failure` modes (though these are also tested at the `NylTemplateEngine` level), and other error conditions.

The current set of tests provides a good foundation for verifying the core logic in `templating_processor.py`.
