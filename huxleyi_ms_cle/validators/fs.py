from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable

from huxleyi_ms_cle.reporting import Finding

BLOCKER = "BLOCKER"
WARN = "WARN"
INFO = "INFO"


def _mk_finding(
    check_id: str,
    severity: str,
    message: str,
    location: str | None = None,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        code=check_id,
        check_id=check_id,
        severity=severity,
        message=message,
        location=location,
        details=details,
    )


def validate_fs_structure(
    root_dir: str | Path,
    required_dirs: Iterable[str] | None = None,
    required_file_patterns: Iterable[str] | None = None,
    warn_extra_dirs: bool = False,
    ignore_dir_patterns: Iterable[str] | None = None,
    *,
    profile: str | None = None,
) -> list[Finding]:
    root = Path(root_dir)
    findings: list[Finding] = []

    required_dirs = list(required_dirs or [])
    required_file_patterns = list(required_file_patterns or [])
    ignore_patterns = list(ignore_dir_patterns or [])

    for required_dir in required_dirs:
        required_path = root / required_dir
        if not required_path.exists() or not required_path.is_dir():
            findings.append(
                _mk_finding(
                    "FS001",
                    BLOCKER,
                    f"Required directory missing: {required_dir}",
                    str(required_path),
                    {"required_dir": required_dir, "profile": profile},
                )
            )

    for pattern in required_file_patterns:
        matches = [path for path in root.glob(pattern) if path.is_file()]
        if not matches:
            findings.append(
                _mk_finding(
                    "FS002",
                    BLOCKER,
                    f"Required file pattern not found: {pattern}",
                    str(root),
                    {"pattern": pattern, "profile": profile},
                )
            )

    if warn_extra_dirs:
        required_top = {str(dirname).split("/")[0] for dirname in required_dirs}
        actual_top = [entry for entry in root.iterdir() if entry.is_dir()]
        for entry in actual_top:
            name = entry.name
            rel = str(entry.relative_to(root)).replace("\\", "/")
            if name in required_top:
                continue
            if any(fnmatch(name, ignore) or fnmatch(rel, ignore) for ignore in ignore_patterns):
                continue
            findings.append(
                _mk_finding(
                    "FS100",
                    WARN,
                    f"Extra directory found: {name}",
                    str(entry),
                    {"directory": name, "profile": profile},
                )
            )

    return findings


def validate_filesystem(workspace: Path, schema: dict[str, Any], profile: str) -> list[Finding]:
    profile_cfg = schema.get("profiles", {}).get(profile, {})
    return validate_fs_structure(
        workspace,
        required_dirs=profile_cfg.get("required_dirs", []),
        required_file_patterns=profile_cfg.get("required_files_glob", []),
        warn_extra_dirs=bool(schema.get("warn_on_extra_dirs", False)),
        ignore_dir_patterns=schema.get("ignore_dirs_glob", []),
        profile=profile,
    )
