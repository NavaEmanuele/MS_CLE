import json
import tempfile
from pathlib import Path

from huxleyi_ms_cle.cli import main


def test_validate_writes_reports_even_if_workspace_missing() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as tdir:
        tmp_path = Path(tdir)
        workspace = tmp_path / "missing_workspace"
        outdir = tmp_path / "out"

        exit_code = main(["validate", str(workspace), "--out", str(outdir)])

        assert exit_code == 2
        report_json = outdir / "report.json"
        report_html = outdir / "report.html"
        assert report_json.exists()
        assert report_html.exists()

        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["summary"]["blocker"] >= 1
