from __future__ import annotations

from pathlib import Path

from huxleyi_ms_cle.cli import main


def test_validate_creates_json_and_html_reports(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "MS1").mkdir(parents=True)
    (workspace / "GeoTec").mkdir(parents=True)
    (workspace / "CLE").mkdir(parents=True)

    out_dir = tmp_path / "out"
    rc = main(["validate", str(workspace), "--out", str(out_dir)])

    assert rc in (0, 2)
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.html").exists()
