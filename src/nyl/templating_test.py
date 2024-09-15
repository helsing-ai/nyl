from nyl.templating import _get_resource_slug


def test_get_resource_slug() -> None:
    assert _get_resource_slug("v1", "Pod", "test") == "test-v1-pod"
    assert (
        _get_resource_slug("verylongapiversion/v1alpha1", "VeryLongResourceName", "longresourcename")
        == "longresourcename-verylongapiversion-v1alpha1-verylongresourcena"
    )
