from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml

from .reporting import Finding


def load_mdb_schema(kind: str, profile: str | None = None, schemas_root: Path | None = None) -> dict[str, Any]:
    del profile  # reserved for profile-specific overrides
    root = schemas_root or Path(os.getenv("HUXLEYI_SCHEMAS_ROOT") or Path(__file__).resolve().parents[1] / "schemas")
    catalog_path = root / "catalog.yaml"
    rel = None
    if catalog_path.exists():
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
        rel = (((catalog.get("kinds") or {}).get(kind) or {}).get("mdb_schema"))
    candidates: list[Path] = []
    if isinstance(rel, str):
        candidates.append(root / rel)
    candidates.append(root / kind / "mdb.yaml")
    for candidate in candidates:
        if candidate.exists():
            payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                return payload
    return {"version": 1, "databases": []}


def find_mdb_files(workspace: Path, globs: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in globs:
        for candidate in workspace.glob(pattern):
            if candidate.is_file() and candidate.suffix.lower() == ".mdb":
                files.append(candidate)
    seen = set()
    ordered: list[Path] = []
    for path in sorted(files):
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def try_read_mdb_tables_pyodbc(mdb_path: Path) -> dict[str, pd.DataFrame]:
    try:
        import pyodbc  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pyodbc not available") from exc

    conn = None
    try:
        conn_str = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            f"DBQ={mdb_path};"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        table_names: list[str] = []
        for row in cursor.tables(tableType="TABLE"):
            name = str(row.table_name)
            if not name.startswith("MSys"):
                table_names.append(name)
        tables: dict[str, pd.DataFrame] = {}
        for table_name in table_names:
            query = f"SELECT * FROM [{table_name}]"
            tables[table_name] = pd.read_sql_query(query, conn)
        return tables
    except Exception as exc:  # pragma: no cover - depends on Access driver
        raise RuntimeError(f"Unable to read MDB via pyodbc: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def write_sqlite(tables: dict[str, pd.DataFrame], sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    try:
        for table_name, dataframe in tables.items():
            dataframe.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    cursor = conn.execute(f"PRAGMA table_info('{table_name}')")
    return [str(row[1]) for row in cursor.fetchall()]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def check_tables_required(sqlite_path: Path, tables_cfg: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    if not sqlite_path.exists():
        return findings

    conn = sqlite3.connect(sqlite_path)
    try:
        for table_def in tables_cfg:
            if not isinstance(table_def, dict):
                continue
            table_name = table_def.get("name")
            required_fields = table_def.get("required_fields", [])
            if not isinstance(table_name, str) or not table_name.strip():
                continue

            if not _table_exists(conn, table_name):
                findings.append(
                    Finding(
                        code="MDB030",
                        check_id="MDB030",
                        severity="BLOCKER",
                        message=f"Required MDB table missing: {table_name}",
                        location=str(sqlite_path),
                        details={"table": table_name},
                    )
                )
                continue

            columns = set(_sqlite_table_columns(conn, table_name))
            if isinstance(required_fields, list):
                for field in required_fields:
                    if isinstance(field, str) and field not in columns:
                        findings.append(
                            Finding(
                                code="MDB030",
                                check_id="MDB030",
                                severity="BLOCKER",
                                message=f"Required MDB field missing: {table_name}.{field}",
                                location=str(sqlite_path),
                                details={"table": table_name, "field": field},
                            )
                        )
    finally:
        conn.close()
    return findings


def _normalize_severity(value: Any, default: str = "WARN") -> str:
    if not isinstance(value, str):
        return default
    severity = value.strip().upper()
    if severity in {"BLOCKER", "WARN", "INFO"}:
        return severity
    return default


def check_relations(
    sqlite_path: Path,
    relations_cfg: list[dict[str, Any]],
    workspace: Path,
    tables_cfg: list[dict[str, Any]] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not sqlite_path.exists():
        return findings

    declared_tables = {
        item.get("name")
        for item in (tables_cfg or [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }

    conn = sqlite3.connect(sqlite_path)
    try:
        for relation in relations_cfg:
            if not isinstance(relation, dict):
                continue
            from_layer = relation.get("from_layer")
            from_field = relation.get("from_field")
            to_table = relation.get("to_table")
            to_field = relation.get("to_field")
            severity = _normalize_severity(relation.get("severity_on_missing"), "WARN")
            if not all(isinstance(v, str) and v.strip() for v in [from_layer, from_field, to_table, to_field]):
                continue

            layer_path = workspace / from_layer
            if not layer_path.exists():
                continue

            try:
                gdf = gpd.read_file(layer_path)
            except Exception as exc:
                findings.append(
                    Finding(
                        code="MDB040",
                        check_id="MDB040",
                        severity="WARN",
                        message=f"Unable to read relation source layer: {from_layer}",
                        location=str(layer_path),
                        details={"error": str(exc)},
                    )
                )
                continue

            if from_field not in gdf.columns:
                findings.append(
                    Finding(
                        code="MDB030",
                        check_id="MDB030",
                        severity="BLOCKER",
                        message=f"Field {from_field} missing in layer {from_layer}",
                        location=from_layer,
                        details={"from_layer": from_layer, "from_field": from_field},
                    )
                )
                continue

            table_exists = _table_exists(conn, to_table)
            if not table_exists:
                if to_table in declared_tables:
                    findings.append(
                        Finding(
                            code="MDB030",
                            check_id="MDB030",
                            severity="BLOCKER",
                            message=f"Required relation table missing: {to_table}",
                            location=str(sqlite_path),
                            details={"to_table": to_table},
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            code="MDB040",
                            check_id="MDB040",
                            severity="WARN",
                            message=f"Relation target table not found: {to_table}",
                            location=str(sqlite_path),
                            details={
                                "to_table": to_table,
                                "hint": "Add table to mdb.yaml tables[] if mandatory, or adjust relation mapping.",
                            },
                        )
                    )
                continue

            columns = _sqlite_table_columns(conn, to_table)
            if to_field not in columns:
                if to_table in declared_tables:
                    findings.append(
                        Finding(
                            code="MDB030",
                            check_id="MDB030",
                            severity="BLOCKER",
                            message=f"Required relation field missing: {to_table}.{to_field}",
                            location=str(sqlite_path),
                            details={"to_table": to_table, "to_field": to_field},
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            code="MDB040",
                            check_id="MDB040",
                            severity="WARN",
                            message=f"Relation target field not found: {to_table}.{to_field}",
                            location=str(sqlite_path),
                            details={
                                "to_table": to_table,
                                "to_field": to_field,
                                "hint": "Add table to mdb.yaml tables[] if mandatory, or adjust relation mapping.",
                            },
                        )
                    )
                continue

            source_ids = sorted({str(v) for v in gdf[from_field].dropna().tolist() if str(v) != ""})
            if not source_ids:
                continue

            conn.execute("DROP TABLE IF EXISTS __tmp_rel_ids")
            conn.execute("CREATE TEMP TABLE __tmp_rel_ids (id_value TEXT)")
            conn.executemany(
                "INSERT INTO __tmp_rel_ids (id_value) VALUES (?)",
                [(value,) for value in source_ids],
            )
            query = (
                f"SELECT t.id_value "
                f"FROM __tmp_rel_ids t "
                f"LEFT JOIN [{to_table}] m ON CAST(m.[{to_field}] AS TEXT) = t.id_value "
                f"WHERE m.[{to_field}] IS NULL"
            )
            missing_values = [str(row[0]) for row in conn.execute(query).fetchall()]
            conn.execute("DROP TABLE IF EXISTS __tmp_rel_ids")

            if missing_values:
                findings.append(
                    Finding(
                        code="MDB040",
                        check_id="MDB040",
                        severity=severity,
                        message=f"Missing references {from_layer}.{from_field} -> {to_table}.{to_field}",
                        location=from_layer,
                        details={
                            "from_layer": from_layer,
                            "from_field": from_field,
                            "to_table": to_table,
                            "to_field": to_field,
                            "missing_count": len(missing_values),
                            "missing_values_sample": missing_values[:3],
                            "relation_type": "missing_references",
                            "operational_class": "RETURN_TO_PROFESSIONAL",
                            "decision": {
                                "can_fix_internally": False,
                                "requires_professional": True,
                                "blocks_submission": True,
                                "needs_manual_review": True,
                            },
                            "workflow": {
                                "assigned_to": "professionista",
                                "status": "open",
                            },
                            "context": {
                                "validation_stage": "mdb_relation_check",
                            },
                            "missing_values_truncated": len(missing_values) > 3,
                        },
                    )
                )
    finally:
        conn.close()
    return findings


def check_tables_and_relations(
    sqlite_path: Path,
    relations: list[dict[str, Any]],
    layers_gdfs: dict[str, Any],
) -> list[Finding]:
    # Backward-compatible helper used by existing tests.
    findings: list[Finding] = []
    conn = sqlite3.connect(sqlite_path)
    try:
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            from_layer = relation.get("from_layer")
            from_field = relation.get("from_field")
            to_table = relation.get("to_table")
            to_field = relation.get("to_field")
            severity = str(relation.get("severity_on_missing", "WARN")).upper()

            if not all(isinstance(v, str) for v in [from_layer, from_field, to_table, to_field]):
                continue
            if from_layer not in layers_gdfs:
                continue
            gdf = layers_gdfs[from_layer]
            if from_field not in gdf.columns:
                findings.append(
                    Finding(
                        code="MDB030",
                        check_id="MDB030",
                        severity="BLOCKER",
                        message=f"Field {from_field} missing in layer {from_layer}",
                        location=from_layer,
                        details={"from_layer": from_layer, "from_field": from_field},
                    )
                )
                continue

            if not _table_exists(conn, to_table):
                findings.append(
                    Finding(
                        code="MDB030",
                        check_id="MDB030",
                        severity="BLOCKER",
                        message=f"Table {to_table} missing in normalized sqlite",
                        location=str(sqlite_path),
                        details={"to_table": to_table},
                    )
                )
                continue

            columns = _sqlite_table_columns(conn, to_table)
            if to_field not in columns:
                findings.append(
                    Finding(
                        code="MDB030",
                        check_id="MDB030",
                        severity="BLOCKER",
                        message=f"Field {to_field} missing in table {to_table}",
                        location=str(sqlite_path),
                        details={"to_table": to_table, "to_field": to_field},
                    )
                )
                continue

            referenced_values = {
                row[0]
                for row in conn.execute(f"SELECT [{to_field}] FROM [{to_table}]").fetchall()
                if row and row[0] is not None
            }
            source_values = {
                value
                for value in gdf[from_field].tolist()
                if value is not None and str(value) != ""
            }
            missing_values = sorted(v for v in source_values if v not in referenced_values)
            if missing_values:
                findings.append(
                    Finding(
                        code="MDB040",
                        check_id="MDB040",
                        severity=severity,
                        message=f"Missing references {from_layer}.{from_field} -> {to_table}.{to_field}",
                        location=from_layer,
                        details={
                            "from_layer": from_layer,
                            "from_field": from_field,
                            "to_table": to_table,
                            "to_field": to_field,
                            "missing_count": len(missing_values),
                            "missing_values_sample": [str(v) for v in missing_values[:20]],
                            "relation_type": "missing_references",
                            "operational_class": "RETURN_TO_PROFESSIONAL",
                            "decision": {
                                "can_fix_internally": False,
                                "requires_professional": True,
                                "blocks_submission": True,
                                "needs_manual_review": True,
                            },
                            "workflow": {
                                "assigned_to": "professionista",
                                "status": "open",
                            },
                            "context": {
                                "validation_stage": "mdb_relation_check",
                            },
                            "missing_values_truncated": len(missing_values) > 20,
                        },
                    )
                )
    finally:
        conn.close()
    return findings


def try_read_mdb_pyodbc(mdb_path: Path) -> dict[str, pd.DataFrame]:
    return try_read_mdb_tables_pyodbc(mdb_path)
