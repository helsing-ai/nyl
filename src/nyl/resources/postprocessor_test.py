from pathlib import Path

from nyl.resources.postprocessor import KyvernoSpec, PostProcessor, PostProcessorSpec
from nyl.tools.types import Manifest, Manifests


def test__PostProcessor__extract_from_list() -> None:
    manifest = Manifests(
        [
            Manifest(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "foo",
                        "namespace": "bar",
                    },
                }
            ),
            Manifest({"apiVersion": "inline.nyl.io/v1", "kind": "PostProcessor", "spec": {"kyverno": {}}}),
        ]
    )

    updated_manifest, processors = PostProcessor.extract_from_list(manifest)
    assert updated_manifest == [manifest[0]]
    assert len(processors) == 1


def test__PostProcessor__process__inlinePolicy() -> None:
    manifest = Manifests(
        [
            # A resource that we expect Kyverno to mutate.
            Manifest(
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
            Manifest(
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

    updated_manifest = processor.process(manifest, Path("/"))

    assert updated_manifest == [
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
