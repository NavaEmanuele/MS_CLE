import json
import shutil
import sqlite3
import uuid
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import Point

import huxleyi_ms_cle.cli as cli_mod
from huxleyi_ms_cle.mdb import check_tables_and_relations


def _new_tmp_dir(prefix: str) -> Path:
    path = Path.cwd() / f".{prefix}_{uuid.uuid4().hex[:10]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_check_tables_and_relations_reports_mdb040() -> None:
    tmp_path = _new_tmp_dir("tmp_test_mdb_rel")
    try:
        sqlite_path = tmp_path / "normalized.sqlite"
        conn = sqlite3.connect(sqlite_path)
        try:
            conn.execute("CREATE TABLE scheda_AC (ID_AC INTEGER)")
            conn.executemany("INSERT INTO scheda_AC (ID_AC) VALUES (?)", [(1,), (2,)])
            conn.commit()
        finally:
            conn.close()

        layer_path = tmp_path / "CLE" / "CL_AC.shp"
        layer_path.parent.mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame({"ID_AC": [1, 3], "geometry": [Point(0, 0), Point(1, 1)]}, crs="EPSG:32633")
        gdf.to_file(layer_path)
        layers_gdfs = {"CLE/CL_AC.shp": gdf}
        relations = [
            {
                "from_layer": "CLE/CL_AC.shp",
                "from_field": "ID_AC",
                "to_table": "scheda_AC",
                "to_field": "ID_AC",
                "severity_on_missing": "WARN",
            }
        ]
        findings = check_tables_and_relations(sqlite_path, relations, layers_gdfs)
        assert any(f.check_id == "MDB040" and f.severity == "WARN" for f in findings)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_validate_reports_mdb010_when_mdb_unreadable(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_mdb_unreadable")
    try:
        schema_root = tmp_path / "schemas_test"
        _write_yaml(
            schema_root / "catalog.yaml",
            {
                "kinds": {
                    "delivery": {
                        "fs_schema": "delivery/fs_structure.yaml",
                        "layers_schema": "delivery/layers.yaml",
                        "topology_schema": "delivery/topology.yaml",
                        "mdb_schema": "delivery/mdb.yaml",
                    }
                }
            },
        )
        _write_yaml(
            schema_root / "delivery" / "fs_structure.yaml",
            {"profiles": {"ms": {"required_dirs": [], "required_files_glob": []}, "cle": {"required_dirs": [], "required_files_glob": []}, "mscle": {"required_dirs": [], "required_files_glob": []}}},
        )
        _write_yaml(schema_root / "delivery" / "layers.yaml", {"version": 1, "layers": []})
        _write_yaml(schema_root / "delivery" / "topology.yaml", {"version": 1, "defaults": {"min_overlap_area": 0.01}, "layers": []})
        _write_yaml(
            schema_root / "delivery" / "mdb.yaml",
            {"version": 1, "mdb_files_glob": ["**/*.mdb"], "tables": [], "relations": []},
        )

        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "fake.mdb").write_text("not-a-real-mdb", encoding="utf-8")
        outdir = tmp_path / "out"

        def _raise(_mdb_path):
            raise RuntimeError("driver missing")

        monkeypatch.setattr(cli_mod, "try_read_mdb_tables_pyodbc", _raise)

        exit_code = cli_mod.main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert any(f["check_id"] == "MDB010" and f["severity"] == "WARN" for f in payload["findings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
