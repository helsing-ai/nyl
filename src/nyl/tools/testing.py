from pathlib import Path


def create_files(prefix: str | Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = Path(prefix) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as file:
            file.write(content)
