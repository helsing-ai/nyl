# Dependency Injection in Nyl

## Overview

Nyl uses a custom dependency injection (DI) system to manage dependencies across commands and services. Each command creates its own request-scoped container, ensuring clean separation of concerns and making testing easier.

## Core Concepts

### DIContainer

The `DIContainer` class (`src/nyl/core/di.py`) provides:

- **Factory registration**: Create instances on demand
- **Singleton registration**: Reuse pre-created instances
- **Type-safe resolution**: Resolve dependencies by type

```python
from nyl.core import DIContainer

container = DIContainer()

# Register a factory
container.register_factory(MyService, lambda: MyService())

# Register a singleton
container.register_singleton(Config, Config())

# Resolve dependencies
service = container.resolve(MyService)
```

### Container Setup Functions

**setup_base_container()** - Registers core dependencies:
- `ProfileManager`
- `ProjectConfig`
- `SecretsConfig`
- `ApiClient`

**setup_service_container()** - Registers service layer:
- `ManifestLoaderService`
- `NamespaceResolverService`
- `KubernetesApplyService`

## Adding New Commands

```python
from pathlib import Path
from nyl.core import DIContainer, setup_base_container
from nyl.project.config import ProjectConfig

@app.command()
def my_command() -> None:
    # Create request-scoped container
    container = DIContainer()
    setup_base_container(container)

    # Resolve dependencies
    project = container.resolve(ProjectConfig)

    # ... command logic ...
```

**Key principles:**
- Create new `DIContainer()` for each command invocation
- Call `setup_base_container()` for core dependencies
- Resolve services via `container.resolve()`

## Adding New Services

1. **Create service class** in `src/nyl/services/`:

```python
class MyNewService:
    def do_something(self) -> None:
        pass
```

2. **Register in container_setup.py**:

```python
def setup_service_container(container: DIContainer, **kwargs) -> None:
    # Stateless service - use singleton
    container.register_singleton(MyNewService, MyNewService())

    # OR with dependencies:
    def _create_service() -> MyNewService:
        dep = container.resolve(Dependency)
        return MyNewService(dep)

    container.register_factory(MyNewService, _create_service)
```

3. **Use in commands**:

```python
service = container.resolve(MyNewService)
service.do_something()
```

## Best Practices

- **Request-scoped containers**: Always create new container per command
- **Factory vs Singleton**: Use factories for lazy init, singletons for stateless services
- **Type safety**: Always resolve by type, not string

## Further Reading

- `src/nyl/core/di.py` - DIContainer implementation
- `src/nyl/core/container_setup.py` - Setup functions
- `src/nyl/services/` - Service implementations
