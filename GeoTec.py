import arcpy # type: ignore
import os

# Imposta l'ambiente di lavoro
arcpy.env.overwriteOutput = True

# Definisci le variabili del comune
COMUNE_NOME = u"NOME_COMUNE"  # Inserisci il nome del tuo comune
COMUNE_CODICE = u"ISTAT"  # Inserisci il codice del tuo comune

# Definisci il percorso base
WORKSPACE_BASE = r"PERCORSO_WORKSPACE"

# Percorso alla cartella GeoTec
WORKSPACE_GEOTEC = os.path.join(WORKSPACE_BASE, "GeoTec")

# Dizionari per popolare il campo DESCR per GeoTec

# Dizionario per Elineari.shp (Tipo_el)
descr_dict_elineari = {
    "5041": "Orlo di scarpata morfologica naturale o artificiale (10-20m)",
    "5042": "Orlo di scarpata morfologica naturale o artificiale (>20m)",
    "5051": "Orlo di terrazzo fluviale (10-20m)",
    "5052": "Orlo di terrazzo fluviale (>20m)",
    "5060": "Cresta",
    "5070": "Scarpata sepolta",
    "5071": "Limite di versante sepolto con inclinazione compresa tra 15° e 45°",
    "5081": "Asse di valle sepolta stretta (C≥ 0.25)*",
    "5082": "Asse di valle sepolta larga (C< 0.25)*",
    "5301": "Asse di paleoalveo",
    "5201": "Limite di campo lavico (ambiente vulcanico)",
    "7011": "Faglia diretta non attiva (certa)",
    "7012": "Faglia diretta non attiva (incerta)",
    "7021": "Faglia inversa non attiva (certa)",
    "7022": "Faglia inversa non attiva (incerta)",
    "7031": "Faglia trascorrente/obliqua non attiva (certa)",
    "7032": "Faglia trascorrente/obliqua non attiva (incerta)",
    "7051": "Faglia con cinematismo non definito non attiva (certa)",
    "7052": "Faglia con cinematismo non definito non attiva (incerta)",
    "5011": "Faglia diretta attiva e capace (certa)",
    "5012": "Faglia diretta attiva e capace (incerta)",
    "5021": "Faglia inversa attiva e capace (certa)",
    "5022": "Faglia inversa attiva e capace (incerta)",
    "5031": "Faglia trascorrente/obliqua attiva e capace (certa)",
    "5032": "Faglia trascorrente/obliqua attiva e capace (incerta)",
    "5001": "Faglia con cinematismo non definito attiva e capace (certa)",
    "5002": "Faglia con cinematismo non definito attiva e capace (incerta)",
    "5111": "Faglia diretta potenzialmente attiva e capace (certa)",
    "5112": "Faglia diretta potenzialmente attiva e capace (incerta)",
    "5121": "Faglia inversa potenzialmente attiva e capace (certa)",
    "5122": "Faglia inversa potenzialmente attiva e capace (incerta)",
    "5131": "Faglia trascorrente/obliqua potenzialmente attiva e capace (certa)",
    "5132": "Faglia trascorrente/obliqua potenzialmente attiva e capace (incerta)",
    "5141": "Faglia con cinematismo non definito potenzialmente attiva e capace (certa)",
    "5142": "Faglia con cinematismo non definito potenzialmente attiva e capace (incerta)",
    "7041": "Sinclinale",
    "7042": "Anticlinale",
    "8001": "Traccia della sezione geologico-tecnica",
    "8002": "Traccia della sezione topografica"
}

# Dizionario per Epuntuali.shp (Tipo_ep)
descr_dict_epuntuali = {
    "6010": "Picco isolato",
    "6020": "Cavità sepolta isolata/sinkhole/dolina"
}

# Dizionario per Forme.shp (Tipo_f)
descr_dict_forme = {
    "4010": "Conoide alluvionale",
    "4020": "Falda detritica",
    "4030": "Area con cavità sepolte/sinkhole/doline",
    "4040": "Ventaglio di lava al piede di pendii o scarpate sepolte",
    "4050": "Superficie suborizzontale sepolta",
    "4060": "Cono o edificio vulcanoclastico sepolto",
    "4070": "Depositi incoerenti sepolti",
    "4080": "Campo di fratturazione cosismica"
}

# Dizionario per Geoidr.shp (Tipo_gi)
descr_dict_geoidr = {
    "11": "Giacitura strati",
    "21": "Pozzo o sondaggio che ha raggiunto il substrato geologico",
    "22": "Pozzo o sondaggio che non ha raggiunto il substrato geologico",
    "31": "Presenza della falda in aree con sabbie e/o ghiaie"
}

# Dizionario per Geotec.shp (Tipo_gt)
descr_dict_geotec = {
    "RI": "Terreni contenenti resti di attività antropica",
    "GW": "Ghiaie pulite con granulometria ben assortita, miscela di ghiaia e sabbie",
    "GP": "Ghiaie pulite con granulometria poco assortita, miscela di ghiaia e sabbia",
    "GM": "Ghiaie limose, miscela di ghiaia, sabbia e limo",
    "GC": "Ghiaie argillose, miscela di ghiaia, sabbia e argilla",
    "SW": "Sabbie pulite e ben assortite, sabbie ghiaiose",
    "SP": "Sabbie pulite con granulometria poco assortita",
    "SM": "Sabbie limose, miscela di sabbia e limo",
    "SC": "Sabbie argillose, miscela di sabbia e argilla",
    "OL": "Limi organici, argille limose organiche di bassa plasticità",
    "OH": "Argille organiche di medio-alta plasticità, limi organici",
    "MH": "Limi inorganici, sabbie fini, limi micacei o diatomacei",
    "ML": "Limi inorganici, farina di roccia, sabbie fini limose o argillose, limi argillosi di bassa plasticità",
    "CL": "Argille inorganiche di medio-bassa plasticità, argille ghiaiose o sabbiose, argille limose, argille magre",
    "CH": "Argille inorganiche di alta plasticità, argille grasse",
    "PT": "Torbe ed altre terre fortemente organiche",
    "LC": "Litoide di copertura",
    "LP": "Substrato geologico lapideo",
    "GR": "Substrato geologico granulare cementato",
    "CO": "Substrato geologico coesivo sovraconsolidato",
    "AL": "Substrato geologico alternanza di litotipi",
    "IS": "Substrato geologico incoerente o poco consolidato",
    "LPS": "Substrato geologico lapideo, stratificato",
    "GRS": "Substrato geologico granulare cementato, stratificato",
    "COS": "Substrato geologico coesivo sovraconsolidato, stratificato",
    "ALS": "Substrato geologico alternanza di litotipi, stratificato",
    "ISS": "Substrato geologico incoerente o poco consolidato, stratificato",
    "SFLP": "Substrato geologico lapideo fratturato / alterato",
    "SFGR": "Substrato geologico granulare cementato fratturato / alterato",
    "SFCO": "Substrato geologico coesivo sovraconsolidato fratturato / alterato",
    "SFAL": "Substrato geologico alternanza di litotipi fratturato / alterato",
    "SFIS": "Substrato geologico incoerente o poco consolidato fratturato / alterato",
    "SFLPS": "Substrato geologico lapideo, stratificato fratturato / alterato",
    "SFGRS": "Substrato geologico granulare cementato, stratificato fratturato / alterato",
    "SFCOS": "Substrato geologico coesivo sovraconsolidato, stratificato fratturato / alterato",
    "SFALS": "Substrato geologico alternanza di litotipi, stratificato fratturato / alterato",
    "SFISS": "Substrato geologico incoerente o poco consolidato, stratificato fratturato / alterato"
}

# Funzioni di Supporto
def add_fields(shapefile, fields_to_add):
    print("\nAggiunta campi a {}".format(shapefile))
    existing_fields = [field.name for field in arcpy.ListFields(shapefile)]
    for field in fields_to_add:
        field_name = field[0]
        field_type = field[1]
        field_length = field[2] if len(field) > 2 else ""
        if field_name not in existing_fields:
            arcpy.AddField_management(shapefile, field_name, field_type, "", "", field_length)
            print("Campo '{}' aggiunto a {}".format(field_name, shapefile))
        else:
            print("Campo '{}' già presente in {}".format(field_name, shapefile))

def populate_comune(shapefile):
    print("Popolamento campo 'Comune' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, ["Comune"]) as cursor:
        for row in cursor:
            row[0] = COMUNE_NOME
            cursor.updateRow(row)
    print("Campo 'Comune' popolato in {}".format(shapefile))

def populate_descr(shapefile, code_field, descr_dict):
    print("Popolamento campo 'DESCR' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, [code_field, "DESCR"]) as cursor:
        for row in cursor:
            code = str(row[0]).strip().upper()
            if code in descr_dict:
                row[1] = descr_dict[code]
            else:
                row[1] = "Tipo {}".format(code)
                print("Codice '{}' non trovato nel dizionario".format(code))
            cursor.updateRow(row)
    print("Campo 'DESCR' popolato in {}".format(shapefile))

# Funzione per elaborare GeoTec
def process_geotec():
    print("\n--- Inizio elaborazione GeoTec per il comune di {} ---".format(COMUNE_NOME))

    # Imposta l'ambiente di lavoro alla cartella GeoTec
    arcpy.env.workspace = WORKSPACE_GEOTEC

    # Lista degli shapefile da elaborare
    shapefiles = ["Epuntuali.shp", "Elineari.shp", "Forme.shp", "Geoidr.shp", "Geotec.shp"]

    for shapefile_name in shapefiles:
        shapefile = os.path.join(WORKSPACE_GEOTEC, shapefile_name)
        if arcpy.Exists(shapefile):
            print("\nElaborazione dello shapefile: {}".format(shapefile))

            # Aggiungi i campi necessari
            fields_to_add = [("Comune", "TEXT", 50), ("DESCR", "TEXT", 255)]
            add_fields(shapefile, fields_to_add)
            # Popola il campo Comune
            populate_comune(shapefile)

            # Popola il campo DESCR utilizzando il dizionario appropriato
            if shapefile_name == "Elineari.shp":
                code_field = "Tipo_el"
                descr_dict = descr_dict_elineari
            elif shapefile_name == "Epuntuali.shp":
                code_field = "Tipo_ep"
                descr_dict = descr_dict_epuntuali
            elif shapefile_name == "Forme.shp":
                code_field = "Tipo_f"
                descr_dict = descr_dict_forme
            elif shapefile_name == "Geoidr.shp":
                code_field = "Tipo_gi"
                descr_dict = descr_dict_geoidr
            elif shapefile_name == "Geotec.shp":
                code_field = "Tipo_gt"
                descr_dict = descr_dict_geotec
            else:
                print("Shapefile '{}' non riconosciuto per l'elaborazione.".format(shapefile_name))
                continue

            # Verifica che il campo code_field esista nello shapefile
            fields = [field.name for field in arcpy.ListFields(shapefile)]
            if code_field not in fields:
                print("ERRORE: Il campo '{}' non esiste nello shapefile '{}'.".format(code_field, shapefile_name))
                continue

            # Popola il campo DESCR
            populate_descr(shapefile, code_field, descr_dict)

        else:
            print("Shapefile '{}' non trovato nella cartella GeoTec.".format(shapefile_name))

    print("\n--- Elaborazione completata per GeoTec del comune di {} ---".format(COMUNE_NOME))

# Esegui la funzione principale
if __name__ == "__main__":
    process_geotec()
