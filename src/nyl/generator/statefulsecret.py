from dataclasses import dataclass

from kubernetes.client.api_client import ApiClient

from nyl.generator import Generator
from nyl.resources.statefulsecret import StatefulSecret
from nyl.tools.types import Resource, ResourceList


@dataclass
class StatefulSecretGenerator(Generator[StatefulSecret], resource_type=StatefulSecret):
    client: ApiClient
    """ Kubernetes API client to use for looking up existing secret state."""

    def generate(self, /, res: StatefulSecret) -> ResourceList:
        # TODO: Look up existing secret state.
        metadata: dict[str, object] = {"name": res.metadata.name}
        if res.metadata.namespace is not None:
            metadata["namespace"] = res.metadata.namespace
        return ResourceList(
            [
                Resource(
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "metadata": metadata,
                        "type": res.type,
                        "stringData": {k: v for k, v in res.stringData.items()},
                    }
                )
            ]
        )
