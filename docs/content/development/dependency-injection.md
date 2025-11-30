# Dependency Injection in Nyl

## Overview

Nyl uses a custom dependency injection (DI) system to manage dependencies across commands and services. The system is built around request-scoped containers, where each command invocation creates its own isolated container instance. This approach ensures clean separation of concerns, makes testing easier, and prevents shared state issues.

## Core Concepts

### DIContainer

The `DIContainer` class (`src/nyl/core/di.py`) is a type-safe dependency injection container that supports:

- **Factory registration**: Register a factory function that creates instances on demand
- **Singleton registration**: Register a pre-created instance to be reused
- **Type-safe resolution**: Resolve dependencies by type with full type checking
- **Scoped containers**: Create child containers that inherit parent registrations
- **Lazy initialization**: Dependencies are only created when first resolved

Example usage:

```python
from nyl.core import DIContainer

container = DIContainer()

# Register a factory (creates new instance each time)
container.register_factory(MyService, lambda: MyService())

# Register a singleton (reuses same instance)
container.register_singleton(Config, Config())

# Resolve dependencies
service = container.resolve(MyService)
config = container.resolve(Config)
```

### ExecutionContext

`ExecutionContext` (`src/nyl/models/context.py`) is a dataclass that encapsulates the state of a command execution. It contains:

- `container`: The DIContainer for this execution
- `project_config`: The resolved ProjectConfig
- `working_dir`: The current working directory

All commands should create an `ExecutionContext` after setting up the container. This provides a clean interface for passing command state through the execution flow.

### TemplateContext

`TemplateContext` extends `ExecutionContext` with additional fields specific to the template command:

- All fields from `ExecutionContext`
- `profile_name`: The Nyl profile being used
- `secrets_provider_name`: The secrets provider name
- `state_dir`: Directory for storing state
- `cache_dir`: Directory for caching data
- `inline`: Whether to evaluate inline resources
- `jobs`: Number of parallel jobs
- `default_namespace`: Default Kubernetes namespace
- `apply_mode`: Whether applying resources
- `diff_mode`: Whether running in diff mode
- `prune`: Whether to prune resources

## Architecture

### Container Setup Functions

The `src/nyl/core/container_setup.py` module provides two key functions for configuring containers:

#### setup_base_container()

Registers foundational dependencies that all commands need:

- `ProfileManager`: Manages Nyl profiles
- `ProjectConfig`: Project configuration
- `SecretsConfig`: Secrets configuration
- `ApiClient`: Kubernetes API client

```python
from nyl.core import DIContainer, setup_base_container

container = DIContainer()
setup_base_container(
    container,
    in_cluster=False,
    profile="my-profile",
    working_dir=Path.cwd(),
)
```

#### setup_service_container()

Registers service layer dependencies:

- `ManifestLoaderService`: Loads and parses YAML manifests
- `NamespaceResolverService`: Resolves namespace for resources
- `KubernetesApplyService`: Handles kubectl apply/diff operations

```python
from nyl.core import setup_service_container

setup_service_container(container, kubectl=kubectl_instance)
```

### Service Layer

The service layer (`src/nyl/services/`) contains business logic extracted from commands:

- **ManifestLoaderService**: Load manifests, extract variables, validate structure
- **NamespaceResolverService**: Resolve and populate namespaces in resources
- **KubernetesApplyService**: Apply/diff resources with ApplySet support
- **ProfileService**: Profile resolution with kubeconfig fallback
- **TemplatingService**: Template evaluation and inline resource handling

Services are stateless and registered as singletons in the container for efficiency.

## Adding New Commands

When creating a new command, follow this pattern:

```python
from pathlib import Path
from typer import Typer

from nyl.core import DIContainer, setup_base_container
from nyl.models.context import ExecutionContext
from nyl.project.config import ProjectConfig

app = Typer()

@app.command()
def my_command() -> None:
    """My command description."""

    # Create DI container for this command execution
    container = DIContainer()
    setup_base_container(container)

    # Create execution context to encapsulate command state
    context = ExecutionContext(
        container=container,
        project_config=container.resolve(ProjectConfig),
        working_dir=Path.cwd(),
    )

    # Resolve dependencies from context container
    project = context.container.resolve(ProjectConfig)

    # ... command logic ...
```

**Key principles:**

1. Create a new `DIContainer()` for each command invocation
2. Call `setup_base_container()` to register core dependencies
3. Create `ExecutionContext` (or `TemplateContext` for template command)
4. Resolve dependencies from `context.container.resolve()` instead of directly from `container`
5. Use the context object to pass command state through the execution flow

## Adding New Services

To add a new service to the DI system:

1. **Create the service class** in `src/nyl/services/`:

```python
class MyNewService:
    """Service description."""

    def do_something(self) -> None:
        """Do something useful."""
        pass
```

2. **Register it in container_setup.py**:

```python
def setup_service_container(container: DIContainer, **kwargs) -> None:
    # ... existing registrations ...

    # Stateless service - use singleton
    container.register_singleton(MyNewService, MyNewService())

    # OR if service has dependencies:
    def _create_my_service() -> MyNewService:
        dependency = container.resolve(SomeDependency)
        return MyNewService(dependency)

    container.register_factory(MyNewService, _create_my_service)
```

3. **Resolve it in commands**:

```python
my_service = context.container.resolve(MyNewService)
my_service.do_something()
```

## Best Practices

### Request-Scoped Containers

Always create a new container for each command invocation. Never share containers between commands or store them globally.

**Good:**
```python
@app.command()
def my_command() -> None:
    container = DIContainer()  # New container per invocation
    setup_base_container(container)
```

**Bad:**
```python
GLOBAL_CONTAINER = DIContainer()  # Don't do this!

@app.command()
def my_command() -> None:
    # Using global container causes shared state issues
```

### Factory vs Singleton Registration

- **Use factories** for services that need lazy initialization or have request-specific dependencies
- **Use singletons** for stateless services or pre-created instances that can be safely shared

```python
# Factory: Creates instance on first resolve
container.register_factory(ApiClient, _create_api_client)

# Singleton: Reuses same instance (good for stateless services)
container.register_singleton(ManifestLoaderService, ManifestLoaderService())
```

### Pass Context Objects

Instead of passing many individual parameters, pass the context object:

**Good:**
```python
def process_manifests(context: TemplateContext) -> None:
    project = context.project_config
    working_dir = context.working_dir
    inline = context.inline
```

**Bad:**
```python
def process_manifests(
    project: ProjectConfig,
    working_dir: Path,
    inline: bool,
    # ... many more parameters
) -> None:
    pass
```

### Type Safety

The DIContainer is fully type-safe. Always resolve by type:

```python
# Good: Type-safe resolution
service = container.resolve(MyService)

# Bad: String-based resolution (not supported)
service = container.resolve("MyService")  # This won't work!
```

## Migration Status

### Completed

- ✅ Created `DIContainer` with factory and singleton support
- ✅ Extracted 5 service classes with 450+ lines of business logic
- ✅ Migrated all commands to use request-scoped containers
- ✅ Integrated `ExecutionContext` and `TemplateContext` throughout commands
- ✅ Removed global `PROVIDER` singleton from command layer
- ✅ All 65+ tests passing with clean type checks

### Current State

Commands using the new DI system:
- `template.py` - Uses `TemplateContext`
- `run.py` - Uses `ExecutionContext`
- `profile.py` - Uses `ExecutionContext`
- `new.py` - Uses `ExecutionContext`
- `tun.py` - Uses `ExecutionContext`
- `secrets.py` - Uses `ExecutionContext`

### Backward Compatibility

The old `DependenciesProvider` system (`src/nyl/tools/di.py`) is kept for backward compatibility with:

- `ProjectConfig.load()` - Still expects `DependenciesProvider`
- `SecretsConfig.load()` - Still expects `DependenciesProvider`

The `container_setup.py` module creates temporary adapters that bridge the new `DIContainer` to the old `DependenciesProvider` for these config modules. This allows gradual migration without breaking existing code.

## Testing

The DI system has comprehensive test coverage in `src/nyl/core/di_test.py`:

- Factory and singleton registration
- Type-safe resolution
- Scoped containers with inheritance
- Parent-child container relationships
- Cache isolation between scopes

When adding new services, write unit tests that:

1. Mock dependencies using the container
2. Test service logic in isolation
3. Verify proper dependency resolution

Example:

```python
def test_my_service():
    container = DIContainer()
    container.register_singleton(Dependency, MockDependency())

    service = container.resolve(MyService)
    result = service.do_something()

    assert result == expected_value
```

## Further Reading

- `src/nyl/core/di.py` - DIContainer implementation
- `src/nyl/core/container_setup.py` - Container setup functions
- `src/nyl/models/context.py` - Context models
- `src/nyl/services/` - Service implementations
- `src/nyl/core/di_test.py` - DI system tests
