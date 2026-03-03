import json
from pathlib import Path

from huxleyi_ms_cle.cli import main


def _touch(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_valid_mscle_workspace(workspace: Path) -> None:
    manifest = {"estimated_profile": "mscle"}
    _touch(workspace / "manifest.json", json.dumps(manifest))
    _touch(workspace / "BasiDati" / "base.mdb")
    _touch(workspace / "CLE" / "CLE.mdb")
    _touch(workspace / "GeoTec" / "geotec.shp")
    _touch(workspace / "Indagini" / "indagini.shp")
    _touch(workspace / "MS1" / "Stab.shp")
    _touch(workspace / "MS1" / "MS1.mdb")
    _touch(workspace / "MS2" / "MS2.mdb")
    _touch(workspace / "Plot" / "CLE" / "sheet.pdf")


def test_validate_writes_reports_even_if_workspace_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "missing_workspace"
    outdir = tmp_path / "out_missing"

    exit_code = main(["validate", str(workspace), "--out", str(outdir)])

    assert exit_code == 2
    report_json = outdir / "report.json"
    report_html = outdir / "report.html"
    assert report_json.exists()
    assert report_html.exists()
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["summary"]["blocker"] >= 1


def test_validate_missing_required_dir_returns_blocker(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace_bad"
    outdir = tmp_path / "out_bad"
    _build_valid_mscle_workspace(workspace)
    (workspace / "MS2" / "MS2.mdb").unlink()
    (workspace / "MS2").rmdir()

    exit_code = main(["validate", str(workspace), "--out", str(outdir)])

    assert exit_code == 2
    payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
    assert payload["summary"]["blocker"] >= 1
    assert any(item["code"] == "FS001" for item in payload["findings"])


def test_validate_workspace_ok_has_no_blockers(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace_ok"
    outdir = tmp_path / "out_ok"
    _build_valid_mscle_workspace(workspace)

    exit_code = main(["validate", str(workspace), "--out", str(outdir)])

    payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["summary"]["blocker"] == 0
