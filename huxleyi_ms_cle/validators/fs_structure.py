from __future__ import annotations

from pathlib import Path
from typing import Iterable

BLOCKER = "BLOCKER"
WARN = "WARN"
OK = "OK"


def _finding(severity: str, code: str, message: str, path: Path | None = None) -> dict:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "path": str(path) if path is not None else "",
    }


def validate_fs_structure(
    root_dir: str | Path,
    required_dirs: Iterable[str] | None = None,
    required_file_patterns: Iterable[str] | None = None,
    warn_extra_dirs: bool = False,
    allowed_extra_dirs: Iterable[str] | None = None,
) -> list[dict]:
    """Validate expected delivery directory structure.

    Args:
        root_dir: Root path of the delivery.
        required_dirs: Directory names/relative paths that must exist under root_dir.
        required_file_patterns: Glob patterns resolved from root_dir that must match >= 1 file.
        warn_extra_dirs: If True, emit WARN findings for unknown top-level directories.
        allowed_extra_dirs: Extra top-level directories allowed when warn_extra_dirs=True.

    Returns:
        A list of findings with coherent schema:
        ``severity``, ``code``, ``message``, ``path``.
    """
    root = Path(root_dir)
    findings: list[dict] = []

    if not root.exists() or not root.is_dir():
        return [
            _finding(
                BLOCKER,
                "ROOT_NOT_FOUND",
                "La cartella radice non esiste o non e' una directory.",
                root,
            )
        ]

    required_dirs = list(required_dirs or [])
    required_file_patterns = list(required_file_patterns or [])
    allowed_extra_dirs_set = set(allowed_extra_dirs or [])

    for rel_dir in required_dirs:
        target = root / rel_dir
        if not target.exists() or not target.is_dir():
            findings.append(
                _finding(
                    BLOCKER,
                    "MISSING_REQUIRED_DIR",
                    "Cartella obbligatoria mancante.",
                    target,
                )
            )

    for pattern in required_file_patterns:
        matches = [p for p in root.glob(pattern) if p.is_file()]
        if not matches:
            findings.append(
                _finding(
                    BLOCKER,
                    "MISSING_REQUIRED_FILE_PATTERN",
                    "Nessun file corrisponde al pattern obbligatorio.",
                    root / pattern,
                )
            )

    if warn_extra_dirs:
        required_top_level = {Path(d).parts[0] for d in required_dirs if Path(d).parts}
        for child in root.iterdir():
            if child.is_dir() and child.name not in required_top_level and child.name not in allowed_extra_dirs_set:
                findings.append(
                    _finding(
                        WARN,
                        "EXTRA_DIR",
                        "Cartella extra non prevista in configurazione.",
                        child,
                    )
                )

    if not findings:
        findings.append(_finding(OK, "STRUCTURE_OK", "Struttura filesystem valida.", root))

    return findings
