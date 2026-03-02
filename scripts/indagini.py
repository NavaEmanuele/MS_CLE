# -*- coding: utf-8 -*-
import arcpy # type: ignore
import os
import re

# Imposta le variabili generali
COMUNE_NOME = u"NOME_COMUNE"  # Inserisci il nome del tuo comune
COMUNE_CODICE = u"ISTAT"  # Inserisci il codice del tuo comune

# Percorsi alle cartelle e database
WORKSPACE_BASE = r""  # Percorso alla cartella\Indagini
MDB_PATH = os.path.join(WORKSPACE_BASE, "PERCORSO_DATABASE")  # Percorso al database MDB
OUTPUT_FOLDER = WORKSPACE_BASE  # Percorso alla cartella di output dove verranno salvati i file .dbf
DOCUMENTS_FOLDER = os.path.join(WORKSPACE_BASE, "Documenti")  # Percorso alla cartella Documenti

# Imposta l'ambiente di lavoro
arcpy.env.overwriteOutput = True
# Percorso alla cartella Indagini
WORKSPACE_INDAGINI = WORKSPACE_BASE

# Dizionario aggiornato per il campo 'cod' (tipo_ind)
descr_dict_indagini = {
    "PA": "Pozzo per Acqua",
    "GG": "Geologia",
    "SS": "Sondaggio a carotaggio continuo che intercetta il substrato",
    "SD": "Sondaggio a distruzione di nucleo",
    "SDS": "Sondaggio a distruzione di nucleo che intercetta il substrato",
    "PI": "Pozzo per Idrocarburi",
    "SMS": "Stratigrafia zona MS (teorica)",
    "S": "Sondaggio a carotaggio continuo",
    "SC": "Sondaggio da cui sono stati prelevati campioni",
    "SP": "Sondaggio con piezometro",
    "SI": "Sondaggio con inclinometro",
    "SPT": "Prova penetrometrica in foro (SPT)",
    "CPT": "Prova penetrometrica statica con punta meccanica (CPT)",
    "CPTE": "Prova penetrometrica statica con punta elettrica",
    "CPTU": "Prova penetrometrica statica con piezocono",
    "DS": "Prova penetrometrica dinamica super pesante",
    "DP": "Prova penetrometrica dinamica pesante",
    "DN": "Prova penetrometrica dinamica media",
    "DL": "Prova penetrometrica dinamica leggera",
    "DMT": "Prova dilatometrica",
    "PP": "Prova pressiometrica",
    "VT": "Prova scissometrica o Vane Test",
    "PLT": "Prova di carico con piastra",
    "SDMT": "Dilatometro sismico",
    "T": "Trincea o pozzetto esplorativo",
    "TP": "Trincea paleosismologica",
    "GEO": "Stazione geomeccanica",
    "SR": "Profilo sismico a rifrazione",
    "SL": "Profilo sismico a riflessione",
    "ERT": "Tomografia elettrica",
    "DH": "Prova sismica in foro tipo Downhole",
    "CH": "Prova sismica in foro tipo Crosshole",
    "UH": "Prova sismica in foro tipo Uphole",
    "REMI": "Prova REfractionMIcrotremors",
    "SCPT": "Prova penetrometrica con cono sismico",
    "ACC": "Stazione accelerometrica / sismometrica",
    "ESAC_SPAC": "Array sismico, ESAC/SPAC",
    "SASW": "SASW",
    "MASW": "MASW",
    "FTAN": "FTAN",
    "SEV": "Sondaggio elettrico verticale",
    "SEO": "Sondaggio elettrico orizzontale",
    "PR": "Profilo di resistività",
    "GM": "Stazione gravimetrica",
    "RAD": "Georadar",
    "HVSR": "Microtremori a stazione singola",
    "ALTRO": "Altro"
}

# Funzione per esportare le tabelle dal database MDB
def export_tables_from_mdb():
    tables_to_export = ["Indagini_Puntuali", "Indagini_Lineari"]

    # Verifica se il database MDB esiste
    if not arcpy.Exists(MDB_PATH):
        print("Errore: Il database MDB non esiste al percorso specificato: {}".format(MDB_PATH))
        return

    print("Il database MDB esiste: {}".format(MDB_PATH))

    # Imposta l'ambiente di lavoro al database MDB
    arcpy.env.workspace = MDB_PATH
    print("Workspace impostato a: {}".format(arcpy.env.workspace))

    # Lista tutte le tabelle presenti nel database MDB
    all_tables = arcpy.ListTables()
    if all_tables is None or len(all_tables) == 0:
        print("Errore: Nessuna tabella trovata nel database MDB.")
        return

    print("Tabelle trovate nel database MDB:")
    for table in all_tables:
        print(" - {}".format(table))

    # Verifica se la cartella di output esiste, altrimenti creala
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print("Cartella di output creata: {}".format(OUTPUT_FOLDER))
    else:
        print("Cartella di output esiste già: {}".format(OUTPUT_FOLDER))

    # Esporta ciascuna tabella specificata
    for table_name in tables_to_export:
        if table_name in all_tables:
            output_table_name = table_name + ".dbf"
            try:
                # Esegui l'esportazione della tabella in formato dBASE
                arcpy.TableToTable_conversion(in_rows=table_name, out_path=OUTPUT_FOLDER, out_name=output_table_name)
                print("Tabella '{}' esportata con successo come '{}'.".format(table_name, output_table_name))
            except arcpy.ExecuteError:
                print("Errore durante l'esportazione della tabella '{}': {}".format(table_name, arcpy.GetMessages()))
        else:
            print("La tabella '{}' non esiste nel database MDB.".format(table_name))

# Funzione per rinominare i file PDF nella directory Documenti
def rename_pdfs_in_directory(directory):
    existing_filenames = {}

    # Ottiene la lista dei file PDF nella directory
    files = [f for f in os.listdir(directory) if f.lower().endswith('.pdf')]
    print("File trovati nella directory '{}': {}".format(directory, files))

    for filename in files:
        old_path = os.path.join(directory, filename)
        base_filename = os.path.splitext(filename)[0]

        new_base_filename = generate_new_filename(base_filename, existing_filenames)
        new_filename = new_base_filename + '.pdf'
        new_path = os.path.join(directory, new_filename)

        if base_filename == new_base_filename:
            print(u"Il file '{}' è già correttamente nominato.".format(filename))
            continue

        if os.path.exists(new_path) and old_path.lower() != new_path.lower():
            print(u"Impossibile rinominare '{}' in '{}': il file esiste già.".format(filename, new_filename))
            continue

        print(u"Rinomino '{}' in '{}'".format(filename, new_filename))
        os.rename(old_path, new_path)

# Funzione per generare il nuovo nome del file PDF
def generate_new_filename(filename, existing_filenames):
    pattern = r'^(\d{6})([PL])(\d+)([A-Z].*)?$'
    match = re.match(pattern, filename)
    if not match:
        print(u"Il nome del file '{}' non corrisponde al pattern atteso.".format(filename))
        return filename

    comune_codice = match.group(1)
    indagine_tipo = match.group(2)
    indagine_numero = match.group(3)

    base_name = "{}{}{}".format(comune_codice, indagine_tipo, indagine_numero)

    count = existing_filenames.get(base_name, 0)
    if count == 0:
        new_name = base_name
    else:
        suffix = chr(ord('a') + count - 1)
        new_name = "{}{}".format(base_name, suffix)

    existing_filenames[base_name] = count + 1
    print("Generato nuovo nome file: '{}' da '{}'".format(new_name, filename))
    return new_name

# Funzione principale
if __name__ == '__main__':
    # 1. Esporta le tabelle dal database MDB
    print("--- Inizio esportazione delle tabelle dal database MDB ---")
    export_tables_from_mdb()
    print("--- Esportazione completata ---")

    # 2. Rinomina i file PDF nella directory "Documenti"
    print("--- Inizio rinomina dei file PDF nella directory Documenti ---")
    if os.path.isdir(DOCUMENTS_FOLDER):
        rename_pdfs_in_directory(DOCUMENTS_FOLDER)
    else:
        print(u"La directory specificata per i documenti non esiste: {}".format(DOCUMENTS_FOLDER))
    print("--- Rinomina dei file PDF completata ---")

    # 3. Esegui lo studio delle indagini
    # Funzione per normalizzare i codici
def normalize_code(code):
    if code is None:
        return ''
    code = str(code).strip().upper()
    # Non rimuovere gli zeri iniziali

    # Utilizza una regex per estrarre il codice base
    match = re.match(r'^(\d{6}[PL]\d+)', code)
    if match:
        code = match.group(1)
    else:
        # Se non corrisponde al pattern, usiamo comunque il codice normalizzato
        pass

    return code

# Funzione per aggiungere campi agli shapefile
def add_fields(shapefile, fields_to_add):
    print(u"\nAggiunta campi a {}".format(shapefile))
    existing_fields = [field.name.upper() for field in arcpy.ListFields(shapefile)]
    for field in fields_to_add:
        field_name = field[0].upper()
        field_type = field[1]
        field_length = field[2] if len(field) > 2 else ""
        if field_name not in existing_fields:
            arcpy.AddField_management(shapefile, field[0], field_type, "", "", field_length)
            print(u"Campo '{}' aggiunto a {}".format(field[0], shapefile))
        else:
            print(u"Campo '{}' già presente in {}".format(field[0], shapefile))

# Funzione per popolare il campo Comune
def populate_comune(shapefile):
    print(u"Popolamento campo 'Comune' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, ["Comune"]) as cursor:
        for row in cursor:
            row[0] = COMUNE_NOME
            cursor.updateRow(row)
    print(u"Campo 'Comune' popolato in {}".format(shapefile))

# Funzione per popolare il campo DESCR utilizzando un dizionario
def populate_descr(shapefile, code_field, descr_dict):
    print(u"Popolamento campo 'DESCR' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, [code_field, "DESCR"]) as cursor:
        for row in cursor:
            code = str(row[0]).strip().upper()  # row[0] è 'cod'
            if code in descr_dict:
                row[1] = descr_dict[code]
            else:
                row[1] = u"Tipo {}".format(code)
                print(u"Codice '{}' non trovato nel dizionario".format(code))
            cursor.updateRow(row)
    print(u"Campo 'DESCR' popolato in {}".format(shapefile))

# Funzione per associare dati dalla tabella allo shapefile
def update_shapefile_from_table(shapefile, table_path, id_field_shp, id_field_table):
    print(u"Aggiornamento dello shapefile '{}' con i dati dalla tabella '{}'".format(shapefile, table_path))
    
    # Verifica se la tabella esiste
    if not arcpy.Exists(table_path):
        print(u"La tabella '{}' non esiste.".format(table_path))
        return
    
    # Verifica i campi nella tabella
    table_fields = [f.name.upper() for f in arcpy.ListFields(table_path)]
    required_fields = [id_field_table.upper(), "TIPO_IND"]
    missing_fields = [f for f in required_fields if f not in table_fields]
    if missing_fields:
        print(u"I seguenti campi mancano nella tabella '{}': {}".format(table_path, ", ".join(missing_fields)))
        return
    
    # Creare un dizionario dai dati della tabella
    indagini_dict = {}
    with arcpy.da.SearchCursor(table_path, [id_field_table, "TIPO_IND"]) as cursor:
        for row in cursor:
            key = normalize_code(row[0])
            indagini_dict[key] = row[1]
    
    # Verifica i campi nello shapefile
    shapefile_fields = [f.name.upper() for f in arcpy.ListFields(shapefile)]
    if "COD" not in shapefile_fields:
        print(u"Il campo 'cod' non esiste nello shapefile '{}'.".format(shapefile))
        return
    
    # Aggiornare lo shapefile utilizzando il dizionario
    fields = [id_field_shp, "cod"]
    with arcpy.da.UpdateCursor(shapefile, fields) as cursor:
        for row in cursor:
            id_value = normalize_code(row[0])
            if id_value in indagini_dict:
                tipo_ind = indagini_dict[id_value]
                row[1] = tipo_ind  # Popola il campo 'cod' con 'tipo_ind' dalla tabella
                cursor.updateRow(row)
            else:
                print(u"ID '{}' non trovato nella tabella.".format(id_value))
    print(u"Shapefile '{}' aggiornato con i dati dalla tabella.".format(shapefile))

# Funzione per popolare il campo URL
def populate_url_indagini(shapefile, id_field):
    print(u"Popolamento campo 'URL' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, [id_field, "URL"]) as cursor:
        for row in cursor:
            id_value = normalize_code(row[0])
            if id_value:
                url = u"https://www.cartografia.servizirl.it/download/sismica/{}.pdf".format(id_value)
                row[1] = url
                cursor.updateRow(row)
            else:
                print(u"ID '{}' non valido per URL".format(row[0]))
    print(u"Campo 'URL' popolato in {}".format(shapefile))

# Funzione per elencare i campi di una tabella (per debugging)
def list_table_fields(table_path):
    fields = [f.name for f in arcpy.ListFields(table_path)]
    print(u"Campi nella tabella '{}': {}".format(table_path, ", ".join(fields)))

# Funzione per elencare i file nella directory per debugging
def list_files_in_directory(directory):
    print("Elenco file in {}:".format(directory))
    for root, dirs, files in os.walk(directory):
        for file in files:
            print(file)

# Funzione principale per elaborare le indagini
def process_indagini():
    print(u"\n--- Inizio elaborazione delle indagini per il comune di {} ---".format(COMUNE_NOME))
    
    # Imposta l'ambiente di lavoro alla cartella delle indagini
    arcpy.env.workspace = WORKSPACE_INDAGINI
    
    # Elenca i file nella directory per debugging
    list_files_in_directory(WORKSPACE_INDAGINI)
    
    # Mapping per gli shapefile
    indagini_mapping = {
        "Ind_pu.shp": {
            "fields": [("Comune", "TEXT", 50), ("cod", "TEXT", 50), ("DESCR", "TEXT", 255), ("URL", "TEXT", 255)],
            "id_shapefile_field": "ID_SPU",
            "id_table_field": "ID_INDPU",
            "table_name": "Indagini_Puntuali"
        },
        "Ind_ln.shp": {
            "fields": [("Comune", "TEXT", 50), ("cod", "TEXT", 50), ("DESCR", "TEXT", 255), ("URL", "TEXT", 255)],
            "id_shapefile_field": "ID_SLN",
            "id_table_field": "ID_INDLN",
            "table_name": "Indagini_Lineari"
        }
    }
    
    for shapefile_name, info in indagini_mapping.items():
        shapefile = os.path.join(WORKSPACE_INDAGINI, shapefile_name)
        table_path = os.path.join(WORKSPACE_INDAGINI, info["table_name"] + ".dbf")
        print("\nVerifica dell'esistenza dello shapefile: {}".format(shapefile))
        
        # Verifica se lo shapefile esiste
        if arcpy.Exists(shapefile):
            print("Shapefile '{}' trovato".format(shapefile))
            # Aggiungi campi
            add_fields(shapefile, info["fields"])
            # Popola il campo Comune
            populate_comune(shapefile)
            # Elenca i campi nella tabella per debugging
            list_table_fields(table_path)
            # Aggiorna lo shapefile con i dati dalla tabella
            update_shapefile_from_table(shapefile, table_path, info["id_shapefile_field"], info["id_table_field"])
            # Popola il campo DESCR utilizzando il dizionario aggiornato
            populate_descr(shapefile, "cod", descr_dict_indagini)
            # Popola il campo URL utilizzando il campo ID
            populate_url_indagini(shapefile, info["id_shapefile_field"])
        else:
            print("Shapefile '{}' non trovato".format(shapefile_name))
    
    print(u"\n--- Elaborazione completata per le indagini del comune di {} ---".format(COMUNE_NOME))

# Funzione principale
def main():
    print("--- Inizio elaborazione per il comune di {} ---".format(COMUNE_NOME))
    process_indagini()
    print("--- Elaborazione completata per il comune di {} ---".format(COMUNE_NOME))

# Esegui la funzione principale
if __name__ == "__main__":
    main()

