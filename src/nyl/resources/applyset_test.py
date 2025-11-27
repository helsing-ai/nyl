from nyl.resources import ObjectMetadata
from nyl.resources.applyset import ApplySet, calculate_applyset_id, get_canonical_resource_kind_name


def test__ApplySet__dump() -> None:
    resource = ApplySet(
        metadata=ObjectMetadata(
            name="test-applyset",
            namespace=None,
        )
    )
    resource.tooling = "kubectl/1.30"
    resource.contains_group_kinds = ["Service", "Deployment.apps"]
    resource.validate()

    assert resource.dump() == {
        "apiVersion": "nyl.io/v1",
        "kind": "ApplySet",
        "metadata": {
            "name": "test-applyset",
            "annotations": {
                "applyset.kubernetes.io/tooling": "kubectl/1.30",
                "applyset.kubernetes.io/contains-group-kinds": "Deployment.apps,Service",  # sorted
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
    # The format is <Kind>.<group> - singular, capitalized Kind name
    assert get_canonical_resource_kind_name("v1", "Pod") == "Pod"
    assert get_canonical_resource_kind_name("apps/v1", "Deployment") == "Deployment.apps"
    assert get_canonical_resource_kind_name("nyl.io/v1", "ApplySet") == "ApplySet.nyl.io"
    assert get_canonical_resource_kind_name("argoproj.io/v1alpha1", "CronWorkflow") == "CronWorkflow.argoproj.io"
