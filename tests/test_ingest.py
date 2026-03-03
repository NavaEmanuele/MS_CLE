import json
import tempfile
import zipfile
from pathlib import Path

from huxleyi_ms_cle.cli import main


def _create_fake_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("dataset_root/CLE/CL_US.shp", "fake-shp-content")
        archive.writestr("dataset_root/MS1/Stab.shp", "fake-ms-content")
        archive.writestr("dataset_root/readme.txt", "example")


def test_ingest_creates_manifest() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as tdir:
        tmp_path = Path(tdir)
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
