from pathlib import Path

TESTDATA_PATH = Path(__file__).parent.parent.parent.parent / "testdata"
assert TESTDATA_PATH.is_dir(), f"testdata directory ({TESTDATA_PATH}) not found"


def create_files(prefix: str | Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = Path(prefix) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as file:
            file.write(content)
