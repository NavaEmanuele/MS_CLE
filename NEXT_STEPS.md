# Next Steps

## Ordine operativo consigliato

1. Estrarre le validazioni da `huxleyi_ms_cle/cli.py` verso `huxleyi_ms_cle/validators/`
   Spostare in moduli dedicati la logica di filesystem, layer, topology e MDB senza cambiare comportamento.

2. Lasciare `cli.py` come orchestratore leggero
   Dopo l'estrazione, `cli.py` deve limitarsi a parsing argomenti, caricamento schema, dispatch e composizione report.

3. Aggiungere o aggiornare test mirati sui moduli `validators`
   Verificare che i test esistenti continuino a passare e coprire il nuovo punto di estensione.

4. Consolidare `schemas/delivery/mdb.yaml`
   Confermare la struttura reale di `CLE_db.mdb` e dichiarare solo tabelle e campi obbligatori effettivi.

5. Completare le relazioni MDB mancanti o ancora provvisorie
   Allineare `relations` ai layer CLE reali e alle tabelle MDB reali.

6. Rendere utili i `domains.yaml`
   Sostituire i placeholder con domini effettivi per i campi piu' critici.

7. Attivare controlli topologici reali in `topology.yaml`
   Configurare almeno i layer poligonali o lineari piu' sensibili.

8. Ripulire i placeholder non usati
   Valutare se implementare o eliminare `reports.py`, `common.py`, `config.py`, `__init__.py` vuoti.

9. Chiarire il supporto a `build --kind incoming`
   O implementarlo davvero, oppure renderlo esplicitamente non supportato.

## Criterio di priorita'

Prima struttura del codice, poi accuratezza delle regole.

La priorita' piu' alta oggi non e' aggiungere nuove validazioni, ma spostare quelle gia' esistenti fuori da `cli.py` per poter evolvere il progetto senza aumentare il debito tecnico.

1. Decidere come trattare `Progetti` e `Vestiture`:
   - warning legittimi
   - oppure cartelle da ignorare/schema da ampliare
2. Analizzare `GEO010` su `urbanizzato_polygon.shp`
3. Valutare se aggiungere un comando o report più esplicito per la baseline Bedizzole
4. Solo dopo: iniziare il refactor di `validators/`