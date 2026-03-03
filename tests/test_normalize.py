import json
import shutil
import uuid
from pathlib import Path

import huxleyi_ms_cle.cli as cli_mod
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


def test_normalize_copies_mdb_files_and_validate_has_no_mdb020(monkeypatch) -> None:
    tmp_path = Path.cwd() / f".tmp_test_normalize_mdb_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        incoming = tmp_path / "incoming_pozzolengo"
        (incoming / "MS23").mkdir(parents=True, exist_ok=True)
        (incoming / "GeoTec").mkdir(parents=True, exist_ok=True)
        (incoming / "CLE").mkdir(parents=True, exist_ok=True)
        (incoming / "Indagini").mkdir(parents=True, exist_ok=True)
        (incoming / "MS23" / "Stab.shp").write_text("fake", encoding="utf-8")
        (incoming / "GeoTec" / "Geotec.shp").write_text("fake", encoding="utf-8")
        (incoming / "Indagini" / "Ind_pu.shp").write_text("fake", encoding="utf-8")
        (incoming / "CLE" / "CLE_db_test.mdb").write_text("", encoding="utf-8")
        (incoming / "Indagini" / "CdI_Tabelle_test.mdb").write_text("", encoding="utf-8")

        out_workspace = tmp_path / "workspace"
        exit_code = main(["normalize", str(incoming), "--out", str(out_workspace), "--kind", "incoming", "--profile", "mscle"])
        assert exit_code == 0

        assert (out_workspace / "GeoTec" / "Geotec.shp").exists()
        assert (out_workspace / "Indagini" / "Ind_pu.shp").exists()
        assert (out_workspace / "MS23" / "Stab.shp").exists()
        assert (out_workspace / "MS2" / "Stab.shp").exists()
        assert (out_workspace / "CLE" / "CLE_db_test.mdb").exists()
        assert (out_workspace / "Indagini" / "CdI_Tabelle_test.mdb").exists()

        manifest = json.loads((out_workspace / "workspace_manifest.json").read_text(encoding="utf-8"))
        assert manifest["copied_files_count"] >= 5
        assert manifest["moved_files_count"] >= 1
        assert any(ex["from"].startswith("MS23/") and ex["to"].startswith("MS2/") for ex in manifest["ms23_to_ms2_examples"])

        def _raise(_path):
            raise RuntimeError("driver unavailable")

        monkeypatch.setattr(cli_mod, "try_read_mdb_pyodbc", _raise)
        outdir = tmp_path / "out_validate"
        _ = cli_mod.main(["validate", str(out_workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "mscle"])
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))

        assert not any(item["check_id"] == "MDB020" for item in payload["findings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
