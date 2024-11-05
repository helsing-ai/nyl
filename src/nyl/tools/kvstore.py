import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, Iterable, TypeVar

from databind.json import dump as ser
from databind.json import load as deser
from filelock import FileLock

T = TypeVar("T")
Value = dict[str, Any] | list[Any] | str | int | float | bool | None


class KvStore(ABC):
    """A simple key-value store interface that can store JSON-like data."""

    @abstractmethod
    def get(self, key: str) -> Value:
        """Get the value for a key."""

    @abstractmethod
    def set(self, key: str, value: Value) -> None:
        """Save a value for a key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a key."""

    @abstractmethod
    def list(self) -> Iterable[str]:
        """List all keys."""


class JsonFileKvStore(KvStore):
    """
    A key-value store that stores data in a JSON file. The file is only saved on exiting the context manager.

    Supports context manager usage to acquire a file lock before reading or writing the file. If a lockfile is
    used, the cached data will be discarded when the lock is released.
    """

    def __init__(self, file: Path, lockfile: Path | None = None) -> None:
        self._path = file
        self._lockfile = FileLock(lockfile) if lockfile else None
        self._data: dict[str, Value] = {}
        self._loaded = False

    def __enter__(self) -> "JsonFileKvStore":
        if self._lockfile:
            self._lockfile.acquire(timeout=5)
        return self

    def __exit__(self, *args: Any) -> None:
        self._save()
        if self._lockfile:
            self._lockfile.release()
            self._data = {}
            self._loaded = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._path})"

    def _load(self) -> None:
        if self._loaded:
            return

        if self._lockfile and not self._lockfile.is_locked:
            raise RuntimeError("File lock must be acquired first (enter JsonFileKvStore context manager)")

        if self._path.exists():
            with self._path.open() as f:
                self._data = json.load(f)
        self._loaded = True

    def _save(self) -> None:
        if self._lockfile and not self._lockfile.is_locked:
            raise RuntimeError("File lock must be acquired first (enter JsonFileKvStore context manager)")

        with self._path.open("w") as f:
            json.dump(self._data, f)

    def get(self, key: str) -> Value:
        assert isinstance(key, str), f"Key must be a string, not {type(key)}"
        self._load()
        return self._data[key]

    def set(self, key: str, value: Value) -> None:
        assert isinstance(key, str), f"Key must be a string, not {type(key)}"
        self._load()
        self._data[key] = value

    def delete(self, key: str) -> None:
        assert isinstance(key, str), f"Key must be a string, not {type(key)}"
        self._load()
        del self._data[key]

    def list(self) -> Iterable[str]:
        self._load()
        return self._data.keys()


class SerializingStore(Generic[T]):
    """
    Store values of a specific type in a key-value store. Values are serialized and deserialized using the
    [databind.json] module.
    """

    def __init__(self, value_type: type[T] | Any, store: KvStore) -> None:
        self._value_type = value_type
        self._store = store

    def __enter__(self) -> "SerializingStore[T]":
        if hasattr(self._store, "__enter__"):
            getattr(self._store, "__enter__")()
        return self

    def __exit__(self, *args: Any) -> None:
        if hasattr(self._store, "__exit__"):
            getattr(self._store, "__exit__")(*args)

    def get(self, key: str) -> T:
        value = self._store.get(key)
        return deser(value, self._value_type, filename=str(self._store))

    def set(self, key: str, value: T) -> None:
        self._store.set(key, ser(value, self._value_type, filename=str(self._store)))

    def delete(self, key: str) -> None:
        self._store.delete(key)

    def list(self) -> Iterable[str]:
        return self._store.list()
