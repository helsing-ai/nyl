from pathlib import Path

from pytest import raises

from nyl.tools.fs import distance_to_cwd


def test_distance_to_cwd() -> None:
    assert distance_to_cwd(Path("foo/bar/baz"), Path("foo/bar/baz/bazinga")) == -1
    assert distance_to_cwd(Path("foo/bar/baz/bazinga"), Path("foo/bar/baz")) == 1
    assert distance_to_cwd(Path("/home/user/"), Path("/home/user/git/projects/mycluster")) == -3
    with raises(ValueError) as excinfo:
        distance_to_cwd(Path("/home/user/nyl-profiles.yaml"), Path("/home/user/git/projects/mycluster"))
    assert (
        str(excinfo.value)
        == "Path '/home/user/nyl-profiles.yaml' is not relative to '/home/user/git/projects/mycluster'"
    )
