"""Tests for the dependency injection container."""

import pytest

from nyl.core.di import DIContainer


class MockDatabase:
    """Mock database for testing."""

    def __init__(self, url: str = "test://db"):
        self.url = url
        self.connected = False

    def connect(self) -> None:
        self.connected = True


class MockCache:
    """Mock cache for testing."""

    def __init__(self, ttl: int = 300):
        self.ttl = ttl


class MockService:
    """Mock service that depends on database."""

    def __init__(self, db: MockDatabase):
        self.db = db


def test_container_register_and_resolve_factory():
    """Test basic factory registration and resolution."""
    container = DIContainer()
    container.register_factory(MockDatabase, lambda: MockDatabase("prod://db"))

    db = container.resolve(MockDatabase)

    assert isinstance(db, MockDatabase)
    assert db.url == "prod://db"


def test_container_factory_creates_singleton():
    """Test that factory only creates one instance."""
    container = DIContainer()
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return MockDatabase()

    container.register_factory(MockDatabase, factory)

    db1 = container.resolve(MockDatabase)
    db2 = container.resolve(MockDatabase)

    assert db1 is db2
    assert call_count == 1


def test_container_register_and_resolve_singleton():
    """Test singleton instance registration."""
    container = DIContainer()
    db = MockDatabase("singleton://db")
    db.connect()

    container.register_singleton(MockDatabase, db)
    resolved = container.resolve(MockDatabase)

    assert resolved is db
    assert resolved.connected


def test_container_resolve_missing_type_raises_key_error():
    """Test that resolving unregistered type raises KeyError."""
    container = DIContainer()

    with pytest.raises(KeyError) as exc_info:
        container.resolve(MockDatabase)

    assert "MockDatabase" in str(exc_info.value)


def test_container_has_checks_registration():
    """Test the has() method for checking registrations."""
    container = DIContainer()

    assert not container.has(MockDatabase)

    container.register_factory(MockDatabase, MockDatabase)

    assert container.has(MockDatabase)


def test_container_create_scope_inherits_from_parent():
    """Test that child scopes can resolve from parent."""
    parent = DIContainer()
    parent.register_factory(MockDatabase, lambda: MockDatabase("parent://db"))

    child = parent.create_scope()
    db = child.resolve(MockDatabase)

    assert db.url == "parent://db"


def test_container_create_scope_has_own_cache():
    """Test that child scopes have independent instance caches."""
    parent = DIContainer()

    # Register factory in parent
    parent.register_factory(MockDatabase, MockDatabase)

    # Create two child scopes
    child1 = parent.create_scope()
    child2 = parent.create_scope()

    # Register different singletons in each child
    cache1 = MockCache(ttl=100)
    cache2 = MockCache(ttl=200)
    child1.register_singleton(MockCache, cache1)
    child2.register_singleton(MockCache, cache2)

    # Each child should have its own cache instance
    assert child1.resolve(MockCache) is cache1
    assert child2.resolve(MockCache) is cache2
    assert child1.resolve(MockCache) is not child2.resolve(MockCache)


def test_container_create_scope_can_override_parent():
    """Test that child scope can override parent registrations."""
    parent = DIContainer()
    parent.register_factory(MockDatabase, lambda: MockDatabase("parent://db"))

    child = parent.create_scope()
    child.register_factory(MockDatabase, lambda: MockDatabase("child://db"))

    # Child should use its own registration
    db = child.resolve(MockDatabase)
    assert db.url == "child://db"

    # Parent should still use original
    parent_db = parent.resolve(MockDatabase)
    assert parent_db.url == "parent://db"


def test_container_clear_removes_all():
    """Test that clear() removes all registrations."""
    container = DIContainer()
    container.register_factory(MockDatabase, MockDatabase)
    container.register_singleton(MockCache, MockCache())

    # Resolve to populate cache
    container.resolve(MockDatabase)

    assert container.has(MockDatabase)
    assert container.has(MockCache)

    container.clear()

    assert not container.has(MockDatabase)
    assert not container.has(MockCache)


def test_container_multiple_types():
    """Test container with multiple registered types."""
    container = DIContainer()
    container.register_factory(MockDatabase, lambda: MockDatabase("multi://db"))
    container.register_factory(MockCache, lambda: MockCache(ttl=600))

    db = container.resolve(MockDatabase)
    cache = container.resolve(MockCache)

    assert db.url == "multi://db"
    assert cache.ttl == 600


def test_container_parent_child_has_check():
    """Test that child's has() checks parent too."""
    parent = DIContainer()
    parent.register_factory(MockDatabase, MockDatabase)

    child = parent.create_scope()

    # Child should see parent's registration
    assert child.has(MockDatabase)

    # Child registers its own type
    child.register_factory(MockCache, MockCache)

    # Child has both
    assert child.has(MockDatabase)
    assert child.has(MockCache)

    # Parent doesn't have child's registration
    assert not parent.has(MockCache)
