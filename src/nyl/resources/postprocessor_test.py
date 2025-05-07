from pathlib import Path

from nyl.resources.postprocessor import KyvernoSpec, PostProcessor, PostProcessorSpec
from nyl.tools.types import Resource, ResourceList


def test__PostProcessor__extract_from_list() -> None:
    input_resources = ResourceList(
        [
            Resource(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "foo",
                        "namespace": "bar",
                    },
                }
            ),
            Resource({"apiVersion": "inline.nyl.io/v1", "kind": "PostProcessor", "spec": {"kyverno": {}}}),
        ]
    )

    updated_resources, processors = PostProcessor.extract_from_list(input_resources)
    assert updated_resources == [input_resources[0]]
    assert len(processors) == 1


def test__PostProcessor__process__inlinePolicy() -> None:
    input_resources = ResourceList(
        [
            # A resource that we expect Kyverno to mutate.
            Resource(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {"name": "foo", "namespace": "foo"},
                    "spec": {
                        "containers": [
                            {
                                "name": "main",
                                "image": "nginx:latest",
                            }
                        ]
                    },
                }
            ),
            # A Service resource that we don't expect it to mutate.
            Resource(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "foo", "namespace": "foo"},
                    "spec": {"selector": {"app": "foo"}},
                }
            ),
        ]
    )

    processor = PostProcessor(
        spec=PostProcessorSpec(
            kyverno=KyvernoSpec(
                inlinePolicies={
                    "security-profile": {
                        "apiVersion": "kyverno.io/v1",
                        "kind": "ClusterPolicy",
                        "metadata": {"name": "enforce-pod-security-context"},
                        "spec": {
                            "validationFailureAction": "enforce",
                            "rules": [
                                {
                                    "name": "mutate-pod-security-context",
                                    "match": {"resources": {"kinds": ["Pod"]}},
                                    "mutate": {
                                        "patchStrategicMerge": {
                                            "spec": {
                                                "securityContext": {
                                                    "runAsNonRoot": True,
                                                    "seccompProfile": {"type": "RuntimeDefault"},
                                                },
                                                "containers": [
                                                    {
                                                        "(name)": "*",
                                                        "securityContext": {
                                                            "runAsNonRoot": True,
                                                            "allowPrivilegeEscalation": False,
                                                            "capabilities": {"drop": ["ALL"]},
                                                        },
                                                    }
                                                ],
                                                "initContainers": [
                                                    {
                                                        "(name)": "*",
                                                        "securityContext": {
                                                            "runAsNonRoot": True,
                                                            "allowPrivilegeEscalation": False,
                                                            "capabilities": {"drop": ["ALL"]},
                                                        },
                                                    }
                                                ],
                                            }
                                        }
                                    },
                                },
                            ],
                        },
                    }
                }
            )
        )
    )

    updated_resources = processor.process(input_resources, Path("/"))

    assert updated_resources == [
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "foo", "namespace": "foo"},
            "spec": {
                "containers": [
                    {
                        "image": "nginx:latest",
                        "name": "main",
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "capabilities": {
                                "drop": [
                                    "ALL",
                                ],
                            },
                            "runAsNonRoot": True,
                        },
                    },
                ],
                "securityContext": {
                    "runAsNonRoot": True,
                    "seccompProfile": {
                        "type": "RuntimeDefault",
                    },
                },
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "foo", "namespace": "foo"},
            "spec": {"selector": {"app": "foo"}},
        },
    ]
