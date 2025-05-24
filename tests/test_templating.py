# tests/test_templating.py
import pytest
from unittest.mock import MagicMock, patch
from argparse import Namespace

from nyl.templating import (
    NylTemplateEngine,
    register,
    registered_functions, # For cleanup if needed
    random_password,
    bcrypt,
    b64decode,
    b64encode,
    lookup,
    LookupError,
    LookupResourceWrapper,
    RESERVED_NAMES
)
from nyl.secrets import SecretProvider
from kubernetes.client.api_client import ApiClient
from kubernetes.dynamic import DynamicClient, ResourceInstance
from kubernetes.client.exceptions import ApiException

from nyl.tools.types import Resource, ResourceList

# --- Fixtures ---

@pytest.fixture
def mock_secret_provider() -> SecretProvider:
    provider = MagicMock(spec=SecretProvider)
    provider.get = MagicMock(return_value="supersecret")
    return provider

@pytest.fixture
def mock_api_client_for_templating() -> ApiClient: # Renamed to avoid conflict
    return MagicMock(spec=ApiClient)

@pytest.fixture
def mock_dynamic_client() -> DynamicClient:
    return MagicMock(spec=DynamicClient)

@pytest.fixture
def template_engine(
    mock_secret_provider: SecretProvider, 
    mock_api_client_for_templating: ApiClient,
    mock_dynamic_client: DynamicClient # Add mock_dynamic_client fixture
) -> NylTemplateEngine:
    engine = NylTemplateEngine(
        secrets=mock_secret_provider, 
        client=mock_api_client_for_templating, 
        on_lookup_failure="Error"
    )
    # Replace the real dynamic_client with our mock for testing lookup
    engine.dynamic_client = mock_dynamic_client
    return engine

# --- Tests for Registered Functions ---

def test_random_password():
    p1 = random_password(16)
    p2 = random_password(16)
    assert isinstance(p1, str)
    assert len(p1) >= 16 # token_urlsafe length can vary slightly
    assert p1 != p2

def test_bcrypt():
    import bcrypt as bcrypt_lib # Import for bcrypt.checkpw
    hashed = bcrypt("testpassword")
    assert isinstance(hashed, str)
    assert bcrypt_lib.checkpw("testpassword".encode('utf-8'), hashed.encode('utf-8'))

def test_b64decode():
    assert b64decode("SGVsbG8gV29ybGQ=") == "Hello World"

def test_b64encode():
    assert b64encode("Hello World") == "SGVsbG8gV29ybGQ="

# --- Tests for NylTemplateEngine.evaluate ---

def test_evaluate_simple_value(template_engine: NylTemplateEngine):
    data = ResourceList([Resource({"key": "static_value"})])
    result = template_engine.evaluate(data)
    assert result[0]["key"] == "static_value"

def test_evaluate_with_secrets(template_engine: NylTemplateEngine, mock_secret_provider: MagicMock):
    data = ResourceList([Resource({"secret_key": "{{ secrets.default.some_key }}"})])
    mock_secret_provider.get.return_value = "my_secret_val"
    
    result = template_engine.evaluate(data)
    assert result[0]["secret_key"] == "my_secret_val"
    mock_secret_provider.get.assert_called_once_with("default", "some_key")

def test_evaluate_with_values(template_engine: NylTemplateEngine):
    template_engine.values.my_var = "hello"
    data = ResourceList([Resource({"val_key": "{{ values.my_var }}"})])
    result = template_engine.evaluate(data)
    assert result[0]["val_key"] == "hello"

def test_evaluate_with_custom_function(template_engine: NylTemplateEngine):
    # Assuming random_password is registered
    data = ResourceList([Resource({"pass": "{{ random_password(8) }}"})])
    result = template_engine.evaluate(data)
    assert isinstance(result[0]["pass"], str)
    assert len(result[0]["pass"]) >= 8


# --- Tests for lookup function and LookupResourceWrapper ---

def test_lookup_success(template_engine: NylTemplateEngine, mock_dynamic_client: MagicMock):
    mock_resource_api = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_resource_api
    
    mock_k8s_object_dict = {"metadata": {"name": "my-obj"}, "spec": {"key": "value"}}
    mock_k8s_resource_instance = ResourceInstance(None, mock_k8s_object_dict) # Adapt as per actual ResourceInstance
    mock_resource_api.get.return_value = mock_k8s_resource_instance

    data = ResourceList([Resource({"config": "{{ lookup('v1', 'ConfigMap', 'my-cm', 'default').spec.key }}"})])
    
    with template_engine.as_current(): # Ensure engine.current is set for lookup
        result = template_engine.evaluate(data)
    
    assert result[0]["config"] == "value"
    mock_dynamic_client.resources.get.assert_called_with(api_version='v1', kind='ConfigMap')
    mock_resource_api.get.assert_called_with(name='my-cm', namespace='default')


def test_lookup_not_found_error_mode(template_engine: NylTemplateEngine, mock_dynamic_client: MagicMock):
    mock_resource_api = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_resource_api
    mock_resource_api.get.side_effect = ApiException(status=404)
    template_engine.on_lookup_failure = "Error"

    data = ResourceList([Resource({"config": "{{ lookup('v1', 'ConfigMap', 'my-cm', 'default').spec.key }}"})])
    
    with template_engine.as_current(), pytest.raises(LookupError):
        template_engine.evaluate(data)

def test_lookup_not_found_skip_resource_mode(template_engine: NylTemplateEngine, mock_dynamic_client: MagicMock):
    mock_resource_api = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_resource_api
    mock_resource_api.get.side_effect = ApiException(status=404)
    template_engine.on_lookup_failure = "SkipResource"

    data = ResourceList([
        Resource({"config": "{{ lookup('v1', 'ConfigMap', 'my-cm', 'default').spec.key }}"}),
        Resource({"key": "value2"}) # Add another resource to ensure list processing continues
    ])
    
    with template_engine.as_current():
        result = template_engine.evaluate(data)
    
    assert len(result) == 1 # First resource was skipped
    assert result[0]["key"] == "value2"


def test_lookup_not_found_create_placeholder_mode(template_engine: NylTemplateEngine, mock_dynamic_client: MagicMock):
    mock_resource_api = MagicMock()
    mock_dynamic_client.resources.get.return_value = mock_resource_api
    mock_resource_api.get.side_effect = ApiException(status=404) # Simulate 404
    template_engine.on_lookup_failure = "CreatePlaceholder"

    # Original resource that will cause lookup failure
    original_resource_spec = Resource({
        "apiVersion": "mygroup.com/v1alpha1",
        "kind": "MyCustomResource",
        "metadata": {"name": "test-cr", "namespace": "cr-ns"},
        "spec": {
            "valueFromLookup": "{{ lookup('v1', 'Secret', 'my-secret', 'default').data.password }}"
        }
    })
    data = ResourceList([original_resource_spec])

    with template_engine.as_current():
        result = template_engine.evaluate(data)

    assert len(result) == 1
    placeholder = result[0]
    assert placeholder["apiVersion"] == "nyl.io/v1"
    assert placeholder["kind"] == "Placeholder"
    assert "test-cr-mygroup-com-v1alpha1-mycustomresource" in placeholder["metadata"]["name"] # Check slugified name
    assert placeholder["metadata"]["namespace"] == "cr-ns"
    assert placeholder["spec"]["reason"] == "LookupError"
    assert "Resource 'Secret/my-secret' not found in namespace 'default'." in placeholder["spec"]["message"]

# --- Test @register decorator ---
def test_register_decorator():
    # Clean up before test if function already exists
    if "my_test_func" in registered_functions:
        del registered_functions["my_test_func"]

    @register(name="my_test_func")
    def _test_func(a: int, b: int) -> int:
        return a + b
    
    assert "my_test_func" in registered_functions
    assert registered_functions["my_test_func"](2, 3) == 5
    del registered_functions["my_test_func"] # Clean up

def test_register_decorator_default_name():
    if "another_test_func" in registered_functions: # Cleanup
        del registered_functions["another_test_func"]

    @register()
    def another_test_func():
        return "hello"
        
    assert "another_test_func" in registered_functions
    assert registered_functions["another_test_func"]() == "hello"
    del registered_functions["another_test_func"] # Clean up

def test_register_decorator_reserved_name():
    with pytest.raises(ValueError, match="Cannot register function with reserved name 'secrets'."):
        @register(name="secrets")
        def _bad_func():
            pass # pragma: no cover
    assert "secrets" not in registered_functions # Ensure it wasn't added despite error
