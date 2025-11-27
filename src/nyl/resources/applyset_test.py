from nyl.resources import ObjectMetadata
from nyl.resources.applyset import ApplySet, _pluralize_kind, calculate_applyset_id, get_canonical_resource_kind_name


def test__ApplySet__dump() -> None:
    resource = ApplySet(
        metadata=ObjectMetadata(
            name="test-applyset",
            namespace=None,
        )
    )
    resource.tooling = "kubectl/1.30"
    resource.contains_group_kinds = ["services", "deployments.apps"]
    resource.validate()

    assert resource.dump() == {
        "apiVersion": "nyl.io/v1",
        "kind": "ApplySet",
        "metadata": {
            "name": "test-applyset",
            "annotations": {
                "applyset.kubernetes.io/tooling": "kubectl/1.30",
                "applyset.kubernetes.io/contains-group-kinds": "deployments.apps,services",  # sorted
            },
            "labels": {
                "applyset.kubernetes.io/id": calculate_applyset_id(
                    name="test-applyset",
                    namespace="",
                    group="nyl.io",
                ),
            },
        },
    }


def test__get_canonical_resource_kind_name() -> None:
    # Without a client, the function falls back to heuristic pluralization (lowercase)
    assert get_canonical_resource_kind_name("v1", "Pod") == "pods"
    assert get_canonical_resource_kind_name("apps/v1", "Deployment") == "deployments.apps"
    assert get_canonical_resource_kind_name("nyl.io/v1", "ApplySet") == "applysets.nyl.io"
    assert get_canonical_resource_kind_name("argoproj.io/v1alpha1", "CronWorkflow") == "cronworkflows.argoproj.io"


def test__pluralize_kind() -> None:
    # Basic pluralization (add 's')
    assert _pluralize_kind("Pod") == "pods"
    assert _pluralize_kind("Deployment") == "deployments"
    assert _pluralize_kind("Service") == "services"
    assert _pluralize_kind("ConfigMap") == "configmaps"
    assert _pluralize_kind("Secret") == "secrets"
    assert _pluralize_kind("CronWorkflow") == "cronworkflows"
    assert _pluralize_kind("Namespace") == "namespaces"

    # Words ending in 's' add 'es'
    assert _pluralize_kind("Ingress") == "ingresses"
    assert _pluralize_kind("Address") == "addresses"

    # Words ending in consonant + 'y' change to 'ies'
    assert _pluralize_kind("NetworkPolicy") == "networkpolicies"
    assert _pluralize_kind("PodSecurityPolicy") == "podsecuritypolicies"

    # Words ending in vowel + 'y' just add 's'
    assert _pluralize_kind("Gateway") == "gateways"

    # Words ending in 'x', 'ch', 'sh' add 'es'
    assert _pluralize_kind("Match") == "matches"
