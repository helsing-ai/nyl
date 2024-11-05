from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from databind.core import Union
from loguru import logger

from kubernetes.client import CoreV1Api, V1ObjectMeta, V1Secret
from kubernetes.client.api_client import ApiClient
from kubernetes.client.exceptions import ApiException
from nyl.secrets import SecretProvider, SecretValue
from nyl.tools.di import DependenciesProvider


@Union.register(SecretProvider, name="KubernetesSecret")
@dataclass
class KubernetesSecretProvider(SecretProvider):
    """
    This secrets provider accesses a Kubernetes secret.

    Needs to be provided with a Kubernetes #ApiClient on init.
    """

    name: str
    namespace: str
    _api: CoreV1Api = field(init=False, repr=False)  # initialized in init()
    _cache: dict[str, str] | None = field(init=False, repr=False, default=None)

    def load(self, force: bool = False) -> dict[str, str]:
        if self._cache is None or force:
            logger.info("Loading secrets from Kubernetes secret '{}/{}'", self.namespace, self.name)
            try:
                _secret = self._api.read_namespaced_secret(self.name, self.namespace)
                self._cache = {k: b64decode(v).decode("utf-8") for k, v in (_secret.data or {}).items()}
            except ApiException as exc:
                if exc.status == 404:
                    logger.warning("Could not find Kubernetes secret '{}/{}'", self.namespace, self.name)
                    self._cache = {}
                else:
                    raise
        return self._cache

    # SecretProvider

    def init(self, config_file: Path, dependencies: DependenciesProvider) -> None:
        self._api = CoreV1Api(api_client=dependencies.get(ApiClient))

    def keys(self) -> Iterable[str]:
        return self.load().keys()

    def get(self, key: str, /) -> SecretValue:
        return self.load()[key]

    def set(self, key: str, value: SecretValue, /) -> None:
        if not isinstance(value, str):
            raise ValueError(f"{type(self).__name__} only supports string values in secrets")
        data = self.load()
        data[key] = value

        # Create or update the Kubernetes secret
        encoded_data = {k: b64encode(v.encode("utf-8")).decode("utf-8") for k, v in data.items()}
        secret = V1Secret(metadata=V1ObjectMeta(name=self.name, namespace=self.namespace), data=encoded_data)
        try:
            self._api.replace_namespaced_secret(self.name, self.namespace, secret)
            logger.info("Updated existing Kubernetes secret '{}/{}'", self.namespace, self.name)
        except ApiException as exc:
            if exc.status == 404:
                self._api.create_namespaced_secret(self.namespace, secret)
                logger.info("Created new Kubernetes secret '{}/{}'", self.namespace, self.name)
            else:
                raise

    def unset(self, key: str, /) -> None:
        data = self.load()
        if key in data:
            del data[key]
            # Update the secret in Kubernetes
            encoded_data = {k: b64encode(v.encode("utf-8")).decode("utf-8") for k, v in data.items()}
            secret = V1Secret(metadata=V1ObjectMeta(name=self.name, namespace=self.namespace), data=encoded_data)
            self._api.replace_namespaced_secret(self.name, self.namespace, secret)
            logger.info("Removed key '{}' from Kubernetes secret '{}/{}'", key, self.namespace, self.name)
        else:
            logger.warning("Key '{}' not found in Kubernetes secret '{}/{}'", key, self.namespace, self.name)
