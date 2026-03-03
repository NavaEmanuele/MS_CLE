# MS_CLE

Raccolta di script **Python + arcpy** per **ArcMap 10.4** (Python 2.7) utili a velocizzare attività ricorrenti nei workflow di:
- **CLE (Condizione Limite per l’Emergenza)**: gestione campi/URL e collegamento a schede e stampe
- **MS (Microzonazione Sismica)**: popolamento descrizioni, URL e pulizia campi (es. MS1)
- **GeoTec**: popolamento descrizioni standard (campi `DESCR`) in base ai codici `Tipo_*`


---

## Requisiti

- **ArcGIS Desktop / ArcMap 10.4**
- **Python 2.7** fornito da ArcGIS Desktop (arcpy)
- Windows (i percorsi sono impostati in stile Windows)

Esecuzione consigliata:
- da **Python Window** di ArcMap
- oppure in **standalone** con il python di ArcGIS (esempio tipico):
  - `C:\Python27\ArcGIS10.4\python.exe <script>.py`

---

## Struttura del repository

- `CLE` → script per shapefile CLE + campi + URL + copia stampe
- `GeoTec` → script per shapefile GeoTec (Elineari/Epuntuali/Forme/Geoidr/Geotec)
- `MS1` → script per shapefile MS1 (Stab/Instab)
- `Indagini` → placeholder (attualmente vuoto)

---

## Script inclusi

### 1) `CLE` (workflow CLE)
Cosa fa (in sintesi):
- Imposta `workspace` e un dizionario `comuni_info` (multi-comune)
- Per gli shapefile `CL_AC`, `CL_AE`, `CL_AS`, `CL_ES`, `CL_US`:
  - aggiunge e/o popola il campo `comune`
  - aggiunge e/o calcola il campo `URL` (link a PDF) usando gli ID (`ID_AC`, `ID_AE`, `ID_AS`, `ID_ES`, `ID_US`)
  - aggiunge `tipologia` (per alcuni layer)
  - per `CL_US` aggiunge/popolare anche `fronte` e `isolato`
- Legge valori da `CLE_db.mdb` (tabelle tipo `scheda_AC`, `scheda_AE`, `scheda_US`) per popolare `tipologia`/campi associati
- Crea una cartella finale immagini/stampe e **copia** i PDF dalle cartelle di stampa nella destinazione

Dove configurare:
- `workspace = "D:\..."` (cartella principale consegna)
- `comuni_info = { ... }` (nome comune, codice, path del `.mdb`)  
- Percorsi “stampe” (cartella `stampe/CLE_<codice>/...`)


---

### 2) `GeoTec` (workflow GeoTec)
Cosa fa (in sintesi):
- Lavora su `GeoTec/Epuntuali.shp`, `Elineari.shp`, `Forme.shp`, `Geoidr.shp`, `Geotec.shp`
- Aggiunge campi:
  - `Comune` (TEXT 50)
  - `DESCR` (TEXT 255)
- Popola `Comune` con `COMUNE_NOME`
- Popola `DESCR` tramite dizionari (mappatura codice → descrizione) in base al campo codice:
  - `Elineari` → `Tipo_el`
  - `Epuntuali` → `Tipo_ep`
  - `Forme` → `Tipo_f`
  - `Geoidr` → `Tipo_gi`
  - `Geotec` → `Tipo_gt`

Dove configurare:
- `COMUNE_NOME`, `COMUNE_CODICE`
- `WORKSPACE_BASE` (cartella base del comune; lo script usa `.../GeoTec`)

---

### 3) `MS1` (workflow MS1)
Cosa fa (in sintesi):
- Lavora su `MS1/Stab.shp` e `MS1/Instab.shp`
- Aggiunge campi:
  - `Comune` (TEXT 50)
  - `DESCR` (TEXT 255)
  - `URL` (TEXT 255)
- Popola `DESCR` da dizionari:
  - `Stab` usando `Tipo_z` (considera i primi 4 caratteri)
  - `Instab` usando `Tipo_i` (considera i primi 6 caratteri)
- Popola `URL` costruendo un link del tipo:
  - `.../<COD_ISTAT>_<COD_TIPO>.jpg`
- Elimina una lista di campi “non necessari” (`FA`, `FV`, `FPGA`, …)

Dove configurare:
- `COMUNE_NOME`, `COMUNE_CODICE`
- `WORKSPACE_BASE` (cartella base del comune; lo script usa `.../MS1`)

---

## Quickstart (procedura consigliata)

1) **Copia** il progetto in una cartella di lavoro locale oppure clona il repo  
2) Apri lo script che ti serve (CLE / GeoTec / MS1)  
3) Modifica in testa:
   - nome comune / codice
   - `WORKSPACE_BASE` / `workspace`
   - eventuali path `.mdb` (solo CLE)
4) Esegui:
   - in ArcMap: Python Window
   - oppure standalone: python di ArcGIS Desktop

---

## Note operative importanti (ArcMap / arcpy)

- Se ArcMap ha layer aperti sugli stessi file, potresti trovarti con lock (`*.lock`). In quel caso chiudi ArcMap o rimuovi i riferimenti ai layer prima di scrivere.
- Usa percorsi raw `r"D:\..."` o raddoppia i backslash


## Autore
Emanuele Nava
