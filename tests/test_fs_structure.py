from pathlib import Path

from huxleyi_ms_cle.validators.fs_structure import BLOCKER, validate_fs_structure


def test_missing_required_directory_is_blocker(tmp_path: Path) -> None:
    (tmp_path / "MS1").mkdir()

    findings = validate_fs_structure(
        root_dir=tmp_path,
        required_dirs=["MS1", "CLE"],
        required_file_patterns=[],
    )

    assert any(
        f["severity"] == BLOCKER and f["code"] == "MISSING_REQUIRED_DIR" and f["path"].endswith("CLE")
        for f in findings
    )
