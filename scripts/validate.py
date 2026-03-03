# -*- coding: utf-8 -*-
"""
Validator base per consegne MS/CLE (ArcMap 10.4 / Python 2.7 / arcpy)

Esegue:
- check struttura (cartelle + shp + mdb se presente)
- check attributi (campi richiesti, null, univocità ID)
- check geometrie (CheckGeometry)
- report CSV + summary TXT

Esecuzione (standalone):
C:\Python27\ArcGIS10.4\python.exe scripts\validate.py --workspace "D:\...\CONSEGNA_COMUNE"

"""
import os
import sys
import re
import csv
import argparse
import datetime
import glob

try:
    import arcpy
except ImportError:
    arcpy = None


# -----------------------------
# Utilities (Py2 safe)
# -----------------------------
def _now_tag():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path):
    if path and (not os.path.isdir(path)):
        os.makedirs(path)


def _to_str(v):
    if v is None:
        return ""
    try:
        # unicode exists in py2
        if isinstance(v, unicode):
            return v.encode("utf-8")
    except Exception:
        pass
    try:
        return str(v)
    except Exception:
        return repr(v)


def _write_csv(rows, out_csv, fieldnames):
    # In Py2, open in binary to avoid blank lines on Windows
    f = open(out_csv, "wb")
    try:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {}
            for k in fieldnames:
                out[k] = _to_str(r.get(k))
            w.writerow(out)
    finally:
        f.close()


def _count(fc):
    return int(arcpy.GetCount_management(fc).getOutput(0))


def _list_fields(fc):
    return {f.name: f for f in arcpy.ListFields(fc)}


def _field_exists(fc, name):
    return name in _list_fields(fc)


def _find_first(pattern):
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _add_issue(issues, severity, component, layer, oid, field, code, message, details=""):
    issues.append({
        "severity": severity,
        "component": component,
        "layer": layer,
        "oid": oid,
        "field": field,
        "code": code,
        "message": message,
        "details": details
    })


# -----------------------------
# Geometry checks
# -----------------------------
def check_geometry(fc, issues, component, out_workspace):
    """
    Usa arcpy.CheckGeometry_management. Output table fields: CLASS, FEATURE_ID, PROBLEM. (ArcMap docs)
    """
    name = os.path.splitext(os.path.basename(fc))[0]
    out_table = os.path.join(out_workspace, "chkgeom_{0}".format(re.sub(r"[^A-Za-z0-9_]", "_", name)))

    if arcpy.Exists(out_table):
        arcpy.Delete_management(out_table)

    arcpy.CheckGeometry_management(fc, out_table)

    n = _count(out_table)
    if n == 0:
        return

    # Output table: CLASS, FEATURE_ID, PROBLEM
    fields = [f.name for f in arcpy.ListFields(out_table)]
    use_fields = []
    for f in ("CLASS", "FEATURE_ID", "PROBLEM"):
        if f in fields:
            use_fields.append(f)

    with arcpy.da.SearchCursor(out_table, use_fields) as cur:
        for row in cur:
            row_d = dict(zip(use_fields, row))
            _add_issue(
                issues,
                "ERROR",
                component,
                name,
                row_d.get("FEATURE_ID", ""),
                "",
                "GEOM_CHECK",
                "Problema geometria: {0}".format(row_d.get("PROBLEM", "")),
                row_d.get("CLASS", "")
            )


def check_overlap(instab_fc, stab_fc, issues, out_workspace, max_rows_to_list=10):
    """
    Controllo overlap semplice tra Instab e Stab via Intersect.
    - Se output non vuoto => WARN
    - Riporta numero intersezioni e (se possibile) qualche coppia di FID.
    """
    out_fc = os.path.join(out_workspace, "tmp_overlap_ms1")
    if arcpy.Exists(out_fc):
        arcpy.Delete_management(out_fc)

    arcpy.Intersect_analysis([instab_fc, stab_fc], out_fc, "ALL", "", "INPUT")

    n = _count(out_fc)
    if n == 0:
        return

    # prova a capire i campi FID_*
    flds = [f.name for f in arcpy.ListFields(out_fc)]
    fid_fields = [f for f in flds if f.upper().startswith("FID_") or f.upper().endswith("_FID")]

    pairs = []
    if fid_fields:
        # prendiamo i primi 2 fid_fields (di solito FID_Instab e FID_Stab)
        use = fid_fields[:2]
        with arcpy.da.SearchCursor(out_fc, use) as cur:
            for i, row in enumerate(cur):
                if i >= max_rows_to_list:
                    break
                pairs.append("{0}={1}, {2}={3}".format(use[0], row[0], use[1], row[1]))

    details = "Intersezioni trovate: {0}".format(n)
    if pairs:
        details += " | esempi: " + "; ".join(pairs)

    _add_issue(
        issues,
        "WARN",
        "MS1",
        "MS1 (Stab/Instab)",
        "",
        "",
        "OVERLAP",
        "Possibile sovrapposizione tra Stab e Instab (verifica soglie micro-overlap).",
        details
    )


# -----------------------------
# Attribute checks
# -----------------------------
def check_required_fields(fc, required_fields, issues, component):
    name = os.path.splitext(os.path.basename(fc))[0]
    fields = _list_fields(fc)

    for rf in required_fields:
        if rf not in fields:
            _add_issue(
                issues, "ERROR", component, name, "", rf, "MISSING_FIELD",
                "Campo obbligatorio mancante", ""
            )


def check_not_null(fc, field_name, issues, component, id_field=None, max_rows=50):
    name = os.path.splitext(os.path.basename(fc))[0]
    if not _field_exists(fc, field_name):
        return

    use_fields = [field_name]
    if id_field and _field_exists(fc, id_field):
        use_fields.append(id_field)
    else:
        id_field = None

    n_found = 0
    with arcpy.da.SearchCursor(fc, use_fields) as cur:
        for row in cur:
            val = row[0]
            if val is None or (isinstance(val, basestring) and val.strip() == ""):
                n_found += 1
                oid = row[1] if id_field else ""
                _add_issue(
                    issues, "ERROR", component, name, oid, field_name, "NULL_VALUE",
                    "Valore nullo/vuoto in campo obbligatorio", ""
                )
                if n_found >= max_rows:
                    break


def check_unique(fc, field_name, issues, component, max_rows=50):
    name = os.path.splitext(os.path.basename(fc))[0]
    if not _field_exists(fc, field_name):
        return

    seen = set()
    dup = []
    with arcpy.da.SearchCursor(fc, [field_name]) as cur:
        for row in cur:
            v = row[0]
            if v is None:
                continue
            if v in seen:
                dup.append(v)
                if len(dup) >= max_rows:
                    break
            else:
                seen.add(v)

    if dup:
        _add_issue(
            issues, "ERROR", component, name, "", field_name, "NOT_UNIQUE",
            "Valori duplicati nel campo che dovrebbe essere univoco", "Esempi: {0}".format(dup[:10])
        )


def check_regex(fc, field_name, pattern, issues, component, id_field=None, max_rows=50):
    name = os.path.splitext(os.path.basename(fc))[0]
    if not _field_exists(fc, field_name):
        return

    rx = re.compile(pattern)
    use_fields = [field_name]
    if id_field and _field_exists(fc, id_field):
        use_fields.append(id_field)
    else:
        id_field = None

    n_found = 0
    with arcpy.da.SearchCursor(fc, use_fields) as cur:
        for row in cur:
            val = row[0]
            if val is None:
                continue
            try:
                s = val.strip()
            except Exception:
                s = str(val)

            if not rx.match(s):
                n_found += 1
                oid = row[1] if id_field else ""
                _add_issue(
                    issues, "WARN", component, name, oid, field_name, "REGEX_FAIL",
                    "Formato valore non conforme", s
                )
                if n_found >= max_rows:
                    break


# -----------------------------
# Validators per macro-sezione
# -----------------------------
def validate_ms1(workspace, issues, run_geom=True, run_overlap=True, out_workspace=None):
    ms1_dir = os.path.join(workspace, "MS1")
    if not os.path.isdir(ms1_dir):
        _add_issue(issues, "ERROR", "MS1", "MS1", "", "", "MISSING_DIR", "Cartella MS1 mancante", ms1_dir)
        return

    stab = _find_first(os.path.join(ms1_dir, "Stab*.shp"))
    instab = _find_first(os.path.join(ms1_dir, "Instab*.shp"))

    if not stab:
        _add_issue(issues, "ERROR", "MS1", "MS1", "", "", "MISSING_SHP", "Shapefile Stab mancante", ms1_dir)
    if not instab:
        _add_issue(issues, "ERROR", "MS1", "MS1", "", "", "MISSING_SHP", "Shapefile Instab mancante", ms1_dir)

    if stab:
        check_required_fields(stab, ["Tipo_z"], issues, "MS1")
        # Se hai già calcolato i campi con lo script, puoi renderli obbligatori qui:
        # check_required_fields(stab, ["Comune","DESCR","URL"], issues, "MS1")
        check_not_null(stab, "Tipo_z", issues, "MS1")
        check_regex(stab, "URL", r"^https?://.+/download/sismica/.+\.jpg$", issues, "MS1")

        if run_geom and out_workspace:
            check_geometry(stab, issues, "MS1", out_workspace)

    if instab:
        check_required_fields(instab, ["Tipo_i"], issues, "MS1")
        # check_required_fields(instab, ["Comune","DESCR","URL"], issues, "MS1")
        check_not_null(instab, "Tipo_i", issues, "MS1")
        check_regex(instab, "URL", r"^https?://.+/download/sismica/.+\.jpg$", issues, "MS1")

        if run_geom and out_workspace:
            check_geometry(instab, issues, "MS1", out_workspace)

    if run_overlap and stab and instab and out_workspace:
        check_overlap(instab, stab, issues, out_workspace)


def validate_geotec(workspace, issues, run_geom=True, out_workspace=None):
    gt_dir = os.path.join(workspace, "GeoTec")
    if not os.path.isdir(gt_dir):
        _add_issue(issues, "ERROR", "GeoTec", "GeoTec", "", "", "MISSING_DIR", "Cartella GeoTec mancante", gt_dir)
        return

    layers = {
        "Elineari": ("Elineari*.shp", ["Tipo_el"]),
        "Epuntuali": ("Epuntuali*.shp", ["Tipo_ep"]),
        "Forme": ("Forme*.shp", ["Tipo_f"]),
        "Geoidr": ("Geoidr*.shp", ["Tipo_gi"]),
        "Geotec": ("Geotec*.shp", ["Tipo_gt"]),
    }

    for name, (pattern, req_fields) in layers.items():
        shp = _find_first(os.path.join(gt_dir, pattern))
        if not shp:
            _add_issue(issues, "WARN", "GeoTec", name, "", "", "MISSING_SHP", "Shapefile mancante (se previsto)", gt_dir)
            continue

        check_required_fields(shp, req_fields, issues, "GeoTec")
        for rf in req_fields:
            check_not_null(shp, rf, issues, "GeoTec")

        if run_geom and out_workspace:
            check_geometry(shp, issues, "GeoTec", out_workspace)


def validate_cle(workspace, issues, run_geom=True, out_workspace=None):
    cle_dir = os.path.join(workspace, "CLE")
    if not os.path.isdir(cle_dir):
        _add_issue(issues, "ERROR", "CLE", "CLE", "", "", "MISSING_DIR", "Cartella CLE mancante", cle_dir)
        return

    cle_layers = {
        "CL_AC": ("CL_AC*.shp", "ID_AC"),
        "CL_AE": ("CL_AE*.shp", "ID_AE"),
        "CL_AS": ("CL_AS*.shp", "ID_AS"),
        "CL_ES": ("CL_ES*.shp", "ID_ES"),
        "CL_US": ("CL_US*.shp", "ID_US"),
    }

    for lname, (pattern, id_field) in cle_layers.items():
        shp = _find_first(os.path.join(cle_dir, pattern))
        if not shp:
            _add_issue(issues, "WARN", "CLE", lname, "", "", "MISSING_SHP", "Shapefile mancante (se previsto)", cle_dir)
            continue

        # ID univoco se esiste
        if _field_exists(shp, id_field):
            check_unique(shp, id_field, issues, "CLE")
            check_not_null(shp, id_field, issues, "CLE")

        # URL e Comune: se presenti, li controlliamo (WARN su regex)
        check_regex(shp, "URL", r"^https?://.+\.pdf$", issues, "CLE", id_field=id_field)
        check_not_null(shp, "comune", issues, "CLE", id_field=id_field)

        if run_geom and out_workspace:
            check_geometry(shp, issues, "CLE", out_workspace)

    # MDB: se presente, controlla tabelle base
    mdb = _find_first(os.path.join(cle_dir, "*.mdb"))
    if mdb:
        try:
            arcpy.env.workspace = mdb
            tables = arcpy.ListTables() or []
            must = ["scheda_AC", "scheda_AE", "scheda_US"]
            for t in must:
                if t not in tables:
                    _add_issue(issues, "WARN", "CLE", "CLE_db.mdb", "", "", "MISSING_TABLE",
                               "Tabella attesa non trovata in MDB (verifica versione/struttura)", t)
        except Exception as ex:
            _add_issue(issues, "WARN", "CLE", "CLE_db.mdb", "", "", "MDB_READ_FAIL",
                       "Impossibile leggere MDB con arcpy (permessi/lock/driver)", str(ex))


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, help="Cartella consegna comune (contiene CLE/MS1/GeoTec)")
    parser.add_argument("--out", default=None, help="Cartella output report (default: <workspace>/_validation)")
    parser.add_argument("--no-geometry", action="store_true", help="Disabilita CheckGeometry")
    parser.add_argument("--no-overlap", action="store_true", help="Disabilita controllo overlap Stab/Instab")
    parser.add_argument(
        "--components",
        default="cle,ms1,geotec",
        help="Componenti da validare (csv tra: cle, ms1, geotec). Default: tutte"
    )
    args = parser.parse_args()

    if arcpy is None:
        print("ERRORE: arcpy non disponibile. Esegui con il Python di ArcGIS Desktop.")
        return 2

    workspace = os.path.abspath(args.workspace)
    out_dir = args.out or os.path.join(workspace, "_validation")
    _ensure_dir(out_dir)

    reports_dir = os.path.join(out_dir, "reports")
    _ensure_dir(reports_dir)

    # Workspace temporaneo per tabelle/fc
    tmp_dir = os.path.join(out_dir, "_tmp")
    _ensure_dir(tmp_dir)
    arcpy.env.workspace = workspace
    arcpy.env.overwriteOutput = True

    issues = []
    tag = _now_tag()

    selected = set([c.strip().lower() for c in args.components.split(",") if c.strip()])
    valid_components = set(["cle", "ms1", "geotec"])
    invalid_components = sorted(selected - valid_components)
    if invalid_components:
        print("ERRORE: componenti non valide: {0}".format(", ".join(invalid_components)))
        print("Usa solo: cle, ms1, geotec")
        return 2
    if not selected:
        selected = valid_components

    # struttura base
    dir_by_component = {
        "cle": "CLE",
        "ms1": "MS1",
        "geotec": "GeoTec",
    }
    for comp in sorted(selected):
        d = dir_by_component.get(comp)
        p = os.path.join(workspace, d)
        if not os.path.isdir(p):
            _add_issue(issues, "ERROR", "STRUCTURE", d, "", "", "MISSING_DIR", "Cartella mancante", p)

    run_geom = (not args.no_geometry)
    run_overlap = (not args.no_overlap)

    if "cle" in selected:
        validate_cle(workspace, issues, run_geom=run_geom, out_workspace=tmp_dir)
    if "ms1" in selected:
        validate_ms1(workspace, issues, run_geom=run_geom, run_overlap=run_overlap, out_workspace=tmp_dir)
    if "geotec" in selected:
        validate_geotec(workspace, issues, run_geom=run_geom, out_workspace=tmp_dir)

    # report
    out_csv = os.path.join(reports_dir, "validation_{0}.csv".format(tag))
    out_txt = os.path.join(reports_dir, "summary_{0}.txt".format(tag))

    fieldnames = ["severity", "component", "layer", "oid", "field", "code", "message", "details"]
    _write_csv(issues, out_csv, fieldnames)

    # summary txt
    counts = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for i in issues:
        sev = i.get("severity", "INFO")
        counts[sev] = counts.get(sev, 0) + 1

    f = open(out_txt, "wb")
    try:
        f.write(_to_str("Workspace: {0}\n".format(workspace)))
        f.write(_to_str("Report CSV: {0}\n".format(out_csv)))
        f.write(_to_str("Totali: ERROR={0} | WARN={1} | INFO={2}\n\n".format(
            counts.get("ERROR", 0), counts.get("WARN", 0), counts.get("INFO", 0)
        )))
        f.write(_to_str("NOTE:\n"))
        f.write(_to_str("- CheckGeometry genera righe con CLASS / FEATURE_ID / PROBLEM.\n"))
        f.write(_to_str("- OVERLAP è un controllo “grezzo”: serve come campanello (micro-overlap da valutare).\n"))
    finally:
        f.close()

    print("OK - Report generati in: {0}".format(reports_dir))
    print("ERROR={0} WARN={1} INFO={2}".format(counts.get("ERROR", 0), counts.get("WARN", 0), counts.get("INFO", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
