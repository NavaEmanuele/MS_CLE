# Project Status

## Stato attuale

Il repository e' gia' utilizzabile come tool CLI schema-driven per i flussi:

- `ingest`
- `normalize`
- `validate`
- `scan`
- `build`

L'entry point reale e' `python -m huxleyi_ms_cle`, che passa da `huxleyi_ms_cle/__main__.py` a `huxleyi_ms_cle/cli.py`.

## Architettura attuale

- `huxleyi_ms_cle/cli.py`
  Orchestratore principale. Contiene parser CLI, caricamento schema, risoluzione `kind` e `profile`, pipeline di ingest/normalize/validate/scan/build e gran parte della logica di validazione.
- `huxleyi_ms_cle/build.py`
  Libreria per il build del delivery package. Applica trasformazioni ai layer, aggiunge campi, valorizza campi derivati, gestisce limiti SHP, scrive SHP/GPKG e zip opzionale.
- `huxleyi_ms_cle/mdb.py`
  Libreria per discovery file `.mdb`, lettura via `pyodbc`, mirror su SQLite e controlli su tabelle, campi e relazioni layer -> MDB.
- `huxleyi_ms_cle/reporting/`
  Sottosistema attivo per modelli report (`Finding`, `Report`, `Summary`) e output `report.json` / `report.html`.
- `huxleyi_ms_cle/validators/`
  Namespace previsto per modularizzare le validazioni, ma attualmente vuoto e non usato.

## Schema e configurazione

- `schemas/catalog.yaml`
  Catalogo centrale che collega `incoming` e `delivery` ai rispettivi schema FS, layers, domains, topology, MDB e mappings.
- `schemas/incoming/fs_structure.yaml`
  Definisce la struttura minima del workspace incoming.
- `schemas/delivery/fs_structure.yaml`
  Definisce la struttura attesa del delivery package.
- `schemas/fs_structure.yaml`
  Fallback legacy che oggi riflette di fatto il layout delivery.

## Componenti complete

- CLI principale funzionante in `huxleyi_ms_cle/cli.py`
- Build delivery operativo in `huxleyi_ms_cle/build.py`
- Gestione MDB operativa in `huxleyi_ms_cle/mdb.py`
- Reporting JSON/HTML operativo in `huxleyi_ms_cle/reporting/`
- Test presenti per `build`, `validate`, `mdb`, `mdb relations`, `ingest`, `normalize`, `scan`
- Schema `layers.yaml` e `build_actions.yaml` gia' concreti e usati dal codice

## Componenti incomplete o vuote

- `huxleyi_ms_cle/validators/__init__.py`
- `huxleyi_ms_cle/validators/ms_validations.py`
- `huxleyi_ms_cle/validators/geometry_checks.py`
- `huxleyi_ms_cle/validators/cle_validations.py`
- `huxleyi_ms_cle/reports.py`
- `huxleyi_ms_cle/common.py`
- `huxleyi_ms_cle/config.py`
- `huxleyi_ms_cle/__init__.py`

Inoltre:

- `domains.yaml` e' quasi placeholder sia per `incoming` sia per `delivery`
- `topology.yaml` ha solo default globali e nessun layer configurato
- `delivery/mdb.yaml` e' solo parzialmente consolidato
- `incoming/mdb.yaml` e' ancora minimale
- il supporto `build --kind incoming` e' formale, ma il build tratta di fatto l'output come delivery

## Obiettivo immediato

Estrarre la logica di validazione da `huxleyi_ms_cle/cli.py` verso `huxleyi_ms_cle/validators/` senza cambiare comportamento, codici finding, schema input o test attesi.

Questo e' il task minimo utile per:

- ridurre il monolite in `cli.py`
- dare un ruolo reale al package `validators`
- preparare il completamento successivo di `domains.yaml`, `topology.yaml` e `mdb.yaml`

## Baseline test — Bedizzole (delivery / mscle)

### Scan
- completata correttamente
- output: `output/bedizzole/scan/layers.json`

### Validate iniziale
- falso positivo `MDB020` su `CLE_db`

### Fix applicata
- aggiornati gli schema:
  - `schemas/delivery/mdb.yaml`
  - `schemas/incoming/mdb.yaml`
  - `schemas/incoming/mappings.yaml`

### Validate dopo fix
- `MDB020` rimosso
- stato baseline attuale:
  - WARN: cartelle extra `Progetti`, `Vestiture`
  - BLOCKER: `GEO010` su `BasiDati/urbanizzato_polygon.shp` con 10 geometrie invalide



  - GEO010 arricchito con dettaglio feature/ID/motivi e decisione operativa
- MDB020 già arricchito in modo retrocompatibile con decisione operativa e contesto


- MDB040 (missing references) arricchito in `huxleyi_ms_cle/mdb.py`
- aggiunti metadati operativi retrocompatibili:
  - relation_type
  - operational_class
  - decision
  - workflow
  - context
  - missing_values_truncated
- altri sotto-casi MDB040 lasciati invariati
