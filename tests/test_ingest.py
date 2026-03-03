import json
import shutil
import uuid
import zipfile
from pathlib import Path

from huxleyi_ms_cle.cli import main


def _create_fake_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("dataset_root/CLE/CL_US.shp", "fake-shp-content")
        archive.writestr("dataset_root/MS1/Stab.shp", "fake-ms-content")
        archive.writestr("dataset_root/readme.txt", "example")


def test_ingest_creates_manifest() -> None:
    tmp_path = Path.cwd() / f".tmp_test_ingest_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        zip_path = tmp_path / "input.zip"
        workspace = tmp_path / "workspace"
        _create_fake_zip(zip_path)

        exit_code = main(["ingest", "--zip", str(zip_path), "--workspace", str(workspace)])

        assert exit_code == 0
        manifest_path = workspace / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["source_zip"].endswith("input.zip")
        assert manifest["estimated_profile"] == "mscle"
        assert (workspace / "CLE" / "CL_US.shp").exists()
        assert (workspace / "MS1" / "Stab.shp").exists()
        assert not (workspace / "dataset_root").exists()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
