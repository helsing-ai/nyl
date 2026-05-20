from unittest.mock import MagicMock

import pytest

from nyl.generator.statefulsecret import StatefulSecretGenerator
from nyl.resources import ObjectMetadata
from nyl.resources.statefulsecret import StatefulSecret


@pytest.fixture
def generator() -> StatefulSecretGenerator:
    return StatefulSecretGenerator(client=MagicMock())


def test__StatefulSecretGenerator__generate__propagates_namespace(
    generator: StatefulSecretGenerator,
) -> None:
    secret = StatefulSecret(
        metadata=ObjectMetadata(name="my-secret", namespace=None),
        stringData={"key": "value"},
    )
    manifests = generator.generate(secret)
    assert len(manifests) == 1
    assert manifests[0]["metadata"].get("namespace") is None

    secret.metadata.namespace = "foo"
    manifests = generator.generate(secret)
    assert len(manifests) == 1
    assert manifests[0]["metadata"]["namespace"] == "foo"


def test__StatefulSecretGenerator__generate__propagates_type(
    generator: StatefulSecretGenerator,
) -> None:
    secret = StatefulSecret(
        metadata=ObjectMetadata(name="my-secret"),
        stringData={"key": "value"},
    )
    manifests = generator.generate(secret)
    assert len(manifests) == 1
    assert manifests[0]["type"] == "Opaque"

    secret.type = "kubernetes.io/dockerconfigjson"
    manifests = generator.generate(secret)
    assert len(manifests) == 1
    assert manifests[0]["type"] == "kubernetes.io/dockerconfigjson"
