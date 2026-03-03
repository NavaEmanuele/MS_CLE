from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .reporting import Finding


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


def check_tables_and_relations(
    sqlite_path: Path,
    relations: list[dict[str, Any]],
    layers_gdfs: dict[str, Any],
) -> list[Finding]:
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

            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (to_table,),
            ).fetchone()
            if table_exists is None:
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
                        },
                    )
                )
    finally:
        conn.close()
    return findings
