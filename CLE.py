# Importa la libreria arcpy
import arcpy
import os
import shutil

# Definisci i percorsi delle directory e dei file
# NOTA: usiamo doppie backslash in tutte le stringhe

workspace = "D:\REGIONE LOMBARDIA\CONSEGNA_MARZO"  # Percorso padre
comuni_info = {
    "Solferino": {
        "nome_display": "Solferino",
        "codice_comune": "020063",
        # Qui inseriamo il nome completo del file .mdb
        "mdb_path": "D:\REGIONE LOMBARDIA\CONSEGNA_MARZO\CLE_Solferino\CLE\CLE_db.mdb"
    }
}  # Dizionario con informazioni sui comuni

# Imposta l'ambiente di lavoro
arcpy.env.workspace = workspace
arcpy.env.overwriteOutput = True

# Carica gli shapefile necessari
shapefiles = ["CL_AC", "CL_AE", "CL_AS", "CL_ES", "CL_US"]

# Funzione per popolare il campo 'comune'
def populate_comune_field(shapefile, comune_display):
    print("Popolando il campo 'comune' per {}...".format(shapefile))
    if len(arcpy.ListFields(shapefile, "comune")) == 0:
        arcpy.AddField_management(shapefile, "comune", "TEXT", field_length=50)
        print("Campo 'comune' aggiunto a {}.".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, ["comune"]) as cursor:
        for row in cursor:
            row[0] = comune_display
            cursor.updateRow(row)
    print("Campo 'comune' popolato per {} con il valore {}.".format(shapefile, comune_display))

# Itera sui comuni e sugli shapefile
for comune, info in comuni_info.items():
    print("Iniziando l'elaborazione per il comune: {}...".format(info.get('nome_display', comune)))
    # Notare come costruiamo il percorso allo shapefile
    comune_workspace = os.path.join(workspace, "CLE_{}".format(comune), "CLE")
    mdb_path = info["mdb_path"]
    codice_comune = info["codice_comune"]
    arcpy.env.workspace = comune_workspace
    
    for shp in shapefiles:
        shp_path = os.path.join(comune_workspace, shp + ".shp")
        if arcpy.Exists(shp_path):
            print("Trovato shapefile: {}".format(shp_path))
            # Aggiungi il campo 'URL' se non esiste
            if len(arcpy.ListFields(shp_path, "URL")) == 0:
                arcpy.AddField_management(shp_path, "URL", "TEXT", field_length=200)
                print("Campo 'URL' aggiunto a {}.".format(shp_path))
            # Aggiungi il campo 'tipologia' se applicabile
            if shp in ["CL_AC", "CL_AE", "CL_US"] and len(arcpy.ListFields(shp_path, "tipologia")) == 0:
                arcpy.AddField_management(shp_path, "tipologia", "TEXT", field_length=200)
                print("Campo 'tipologia' aggiunto a {}.".format(shp_path))
            # Aggiungi i campi 'fronte' e 'isolato' per CL_US
            if shp == "CL_US":
                if len(arcpy.ListFields(shp_path, "fronte")) == 0:
                    arcpy.AddField_management(shp_path, "fronte", "SHORT")
                    print("Campo 'fronte' aggiunto a {}.".format(shp_path))
                if len(arcpy.ListFields(shp_path, "isolato")) == 0:
                    arcpy.AddField_management(shp_path, "isolato", "SHORT")
                    print("Campo 'isolato' aggiunto a {}.".format(shp_path))
            # Popola il campo 'comune'
            populate_comune_field(shp_path, info.get('nome_display', comune))

# Funzione per calcolare il campo URL
def populate_url(shapefile, id_field, prefix):
    print("Popolando il campo 'URL' per {}...".format(shapefile))
    url_expr = '"http://www.cartografia.regione.lombardia.it/download/sismica/CLE/{}_" + str(!{}!) + ".pdf"'.format(prefix, id_field)
    arcpy.CalculateField_management(shapefile, "URL", url_expr, "PYTHON_9.3")
    print("Campo 'URL' popolato per {}.".format(shapefile))

# Popola il campo URL per ciascuno shapefile
for comune, info in comuni_info.items():
    print("Iniziando il popolamento del campo 'URL' per il comune: {}...".format(comune))
    comune_workspace = os.path.join(workspace, "CLE_{}".format(comune), "CLE")
    arcpy.env.workspace = comune_workspace
    
    for shp in shapefiles:
        shp_path = os.path.join(comune_workspace, shp + ".shp")
        if arcpy.Exists(shp_path):
            if shp == "CL_AC":
                populate_url(shp_path, "ID_AC", "AC")
            elif shp == "CL_AE":
                populate_url(shp_path, "ID_AE", "AE")
            elif shp == "CL_AS":
                populate_url(shp_path, "ID_AS", "AS")
            elif shp == "CL_ES":
                populate_url(shp_path, "ID_ES", "ES")
            elif shp == "CL_US":
                populate_url(shp_path, "ID_US", "US")

# Popola il campo 'tipologia' per CL_AC, CL_AE e CL_US
for comune, info in comuni_info.items():
    print("Popolamento del campo 'tipologia' per CL_AC, CL_AE e CL_US per il comune: {}...".format(comune))
    comune_workspace = os.path.join(workspace, "CLE_{}".format(comune), "CLE")
    mdb_path = info["mdb_path"]
    
    # Popola il campo tipologia per CL_AC
    cl_ac_table = os.path.join(mdb_path, "scheda_AC")
    if arcpy.Exists(cl_ac_table):
        tipo_infra_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(cl_ac_table, ["ID_AC", "tipo_infra"])}
        cl_ac_shapefile = os.path.join(comune_workspace, "CL_AC.shp")
        if arcpy.Exists(cl_ac_shapefile):
            with arcpy.da.UpdateCursor(cl_ac_shapefile, ["ID_AC", "tipologia"]) as cursor:
                for row in cursor:
                    if row[0] in tipo_infra_dict:
                        tipo_infra = tipo_infra_dict[row[0]]
                        if tipo_infra == 1:
                            row[1] = "Accessibilità"
                        elif tipo_infra == 2:
                            row[1] = "Connessione"
                        cursor.updateRow(row)
            print("Campo 'tipologia' popolato per CL_AC.")
    
    # Popola il campo tipologia per CL_AE
    cl_ae_table = os.path.join(mdb_path, "scheda_AE")
    if arcpy.Exists(cl_ae_table):
        tipo_area_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(cl_ae_table, ["ID_AE", "tipo_area"])}
        cl_ae_shapefile = os.path.join(comune_workspace, "CL_AE.shp")
        if arcpy.Exists(cl_ae_shapefile):
            with arcpy.da.UpdateCursor(cl_ae_shapefile, ["ID_AE", "tipologia"]) as cursor:
                for row in cursor:
                    if row[0] in tipo_area_dict:
                        tipo_area = tipo_area_dict[row[0]]
                        if tipo_area == 1:
                            row[1] = "Ammassamento"
                        elif tipo_area == 2:
                            row[1] = "Ricovero"
                        elif tipo_area == 3:
                            row[1] = "Ammassamento-Ricovero"
                        cursor.updateRow(row)
            print("Campo 'tipologia' popolato per CL_AE.")
    
    # Popola il campo tipologia per CL_US
    cl_us_table = os.path.join(mdb_path, "scheda_US")
    if arcpy.Exists(cl_us_table):
        us_data_dict = {row[0]: (row[1], row[2]) for row in arcpy.da.SearchCursor(cl_us_table, ["ID_US", "fronte", "isolato"])}
        cl_us_shapefile = os.path.join(comune_workspace, "CL_US.shp")
        if arcpy.Exists(cl_us_shapefile):
            with arcpy.da.UpdateCursor(cl_us_shapefile, ["ID_US", "fronte", "isolato", "tipologia"]) as cursor:
                for row in cursor:
                    if row[0] in us_data_dict:
                        fronte, isolato = us_data_dict[row[0]]
                        row[1] = fronte
                        row[2] = isolato
                        if isolato == 1:
                            row[3] = "Unità strutturale interferente isolata"
                        elif fronte == 0 and isolato == 0:
                            row[3] = "Unità strutturale non interferente appartenente ad un AS"
                        elif fronte == 1 and isolato == 0:
                            row[3] = "Unità strutturale interferente appartenente ad un AS"
                        cursor.updateRow(row)
            print("Campo 'tipologia' popolato per CL_US.")

# Funzione per creare una cartella e spostare i PDF
def create_and_move_pdfs(comune, codice_comune, workspace):
    print("Creazione della cartella di destinazione per i PDF del comune: {}...".format(comune))
    # Definisci il percorso della cartella delle stampe e della destinazione
    stampe_workspace = os.path.join(workspace, "stampe", "CLE_{}".format(codice_comune))
    comune_workspace = os.path.join(workspace, "CLE_{}".format(comune), "CLE")
    destinazione_cartella = os.path.join(comune_workspace, "{}_immagini_finali_CLE".format(comune.replace('_', ' ')))
    
    # Crea la cartella di destinazione se non esiste
    if not os.path.exists(destinazione_cartella):
        os.makedirs(destinazione_cartella)
        print("Cartella {} creata.".format(destinazione_cartella))
    
    # Itera sulle cartelle archivio e copia i PDF nella cartella finale
    for archivio_tipo in ["scheda_AC", "scheda_AE", "scheda_AS", "scheda_ES", "scheda_US"]:
        archivio_cartella = os.path.join(stampe_workspace, archivio_tipo)
        if os.path.exists(archivio_cartella):
            print("Copia dei PDF dalla cartella {} alla cartella {}...".format(archivio_cartella, destinazione_cartella))
            for pdf_file in os.listdir(archivio_cartella):
                if pdf_file.endswith(".pdf"):
                    src_pdf_path = os.path.join(archivio_cartella, pdf_file)
                    dst_pdf_path = os.path.join(destinazione_cartella, pdf_file)
                    shutil.copy(src_pdf_path, dst_pdf_path)
    print("Copia dei PDF completata per il comune: {}".format(comune))

# Sposta i PDF nelle cartelle finali per ogni comune
for comune, info in comuni_info.items():
    create_and_move_pdfs(comune, info["codice_comune"], workspace)

print("Processo completato. Shapefile e PDF aggiornati.")
