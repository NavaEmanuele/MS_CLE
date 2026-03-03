from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

SUPPORTED_VECTOR_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_zip(zip_path: Path, destination: Path) -> list[Path]:
    ensure_dir(destination)
    with ZipFile(zip_path, "r") as archive:
        archive.extractall(destination)
    return list(destination.rglob("*"))


def discover_vector_files(workspace: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in workspace.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_VECTOR_EXTENSIONS
        ]
    )
