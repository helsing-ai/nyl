from dataclasses import dataclass

from kubernetes.client.api_client import ApiClient
from nyl.generator import Generator
from nyl.resources.statefulsecret import StatefulSecret
from nyl.tools.types import Manifest, Manifests


@dataclass
class StatefulSecretGenerator(Generator[StatefulSecret], resource_type=StatefulSecret):
    client: ApiClient
    """ Kubernetes API client to use for looking up existing secret state."""

    def generate(self, /, res: StatefulSecret) -> Manifests:
        # TODO: Look up existing secret state.
        return Manifests(
            [
                Manifest(
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": {"name": res.metadata.name},
                        "stringData": {k: v for k, v in res.stringData.items()},
                    }
                )
            ]
        )
