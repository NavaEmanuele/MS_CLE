import json
import shutil
import uuid
from pathlib import Path

from huxleyi_ms_cle.cli import main


def test_normalize_creates_workspace_and_manifest() -> None:
    tmp_path = Path.cwd() / f".tmp_test_normalize_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        incoming = tmp_path / "incoming_pkg"
        incoming.mkdir(parents=True, exist_ok=True)
        (incoming / "raw.txt").write_text("raw", encoding="utf-8")

        out_workspace = tmp_path / "workspace"
        exit_code = main(["normalize", str(incoming), "--out", str(out_workspace)])

        assert exit_code == 0
        assert out_workspace.exists()
        manifest_path = out_workspace / "workspace_manifest.json"
        assert manifest_path.exists()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["kind"] == "incoming"
        assert "created_dirs" in payload
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_normalize_maps_ms23_to_ms2() -> None:
    tmp_path = Path.cwd() / f".tmp_test_normalize_map_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        incoming = tmp_path / "incoming_pozzolengo"
        (incoming / "MS23").mkdir(parents=True, exist_ok=True)
        (incoming / "MS23" / "Stab.shp").write_text("fake-shp", encoding="utf-8")

        out_workspace = tmp_path / "workspace"
        exit_code = main(["normalize", str(incoming), "--out", str(out_workspace), "--kind", "incoming", "--profile", "ms"])

        assert exit_code == 0
        mapped_path = out_workspace / "MS2" / "Stab.shp"
        assert mapped_path.exists()

        manifest = json.loads((out_workspace / "workspace_manifest.json").read_text(encoding="utf-8"))
        assert any(item["source"].endswith("MS23\\Stab.shp") or item["source"].endswith("MS23/Stab.shp") for item in manifest["mapped_items"])
        assert any(item["dest"].endswith("MS2\\Stab.shp") or item["dest"].endswith("MS2/Stab.shp") for item in manifest["mapped_items"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
