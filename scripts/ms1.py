# -*- coding: utf-8 -*-
import arcpy
import os

# Imposta l'ambiente di lavoro
arcpy.env.overwriteOutput = True

# Definisci le variabili del comune
COMUNE_NOME = u"NOME_COMUNE"       # Nome del comune
COMUNE_CODICE = u"CODICE_ISTAT"    # Codice ISTAT del comune

# Definisci il percorso base
WORKSPACE_BASE = r""

# Percorso alla cartella MS1
WORKSPACE_MS1 = os.path.join(WORKSPACE_BASE, "MS1")

# Dizionario per popolare il campo DESCR per Stab.shp
descr_dict_stab = {
    "1011": "Lapideo / stratificato",
    "1012": "Lapideo / non stratificato",
    "1021": "Granulare cementato / stratificato",
    "1022": "Granulare cementato / non stratificato",
    "1031": "Coesivo sovraconsolidato / stratificato",
    "1032": "Coesivo sovraconsolidato / non stratificato",
    "1041": "Alternanze litologiche / stratificato",
    "1042": "Alternanze litologiche / non stratificato",
    "2099": "Substrato fratturato o alterato",
    "2001": "Zona stabile suscettibile di amplificazione 1",
    "2002": "Zona stabile suscettibile di amplificazione 2",
    "2003": "Zona stabile suscettibile di amplificazione 3",
    "2004": "Zona stabile suscettibile di amplificazione 4",
    "2005": "Zona stabile suscettibile di amplificazione 5",
    "2006": "Zona stabile suscettibile di amplificazione 6",
    "2007": "Zona stabile suscettibile di amplificazione 7",
    "2008": "Zona stabile suscettibile di amplificazione 8",
    "2009": "Zona stabile suscettibile di amplificazione 9",
    "2010": "Zona stabile suscettibile di amplificazione 10",
    "2011": "Zona stabile suscettibile di amplificazione 11",
    "2012": "Zona stabile suscettibile di amplificazione 12",
    "2013": "Zona stabile suscettibile di amplificazione 13",
    "2014": "Zona stabile suscettibile di amplificazione 14",
    "2015": "Zona stabile suscettibile di amplificazione 15",
    "2016": "Zona stabile suscettibile di amplificazione 16"
}

# Dizionario per popolare il campo DESCR per Instab.shp
descr_dict_instab = {
    "300120": "Zona di Suscettibilità per le instabilità di versante",
    "300220": "Zona di Rispetto per le instabilità di versante",
    "305220": "Zona di Suscettibilità per la liquefazione",
    "305320": "Zona di Rispetto per la liquefazione",
    "3061": "Zona di Suscettibilità per faglie attive e capaci",
    "3062": "Zona di Rispetto per faglie attive e capaci",
    "301120": "Zona di attenzione per Instabilità di versante Attiva / crollo o ribaltamento",
    "301220": "Zona di attenzione per Instabilità di versante Attiva / scorrimento",
    "301320": "Zona di attenzione per Instabilità di versante Attiva / colata",
    "301420": "Zona di attenzione per Instabilità di versante Attiva / complessa",
    "301520": "Zona di attenzione per Instabilità di versante Attiva / non definito",
    "302120": "Zona di attenzione per Instabilità di versante Quiescente / crollo o ribaltamento",
    "302220": "Zona di attenzione per Instabilità di versante Quiescente / scorrimento",
    "302320": "Zona di attenzione per Instabilità di versante Quiescente / colata",
    "302420": "Zona di attenzione per Instabilità di versante Quiescente / complessa",
    "302520": "Zona di attenzione per Instabilità di versante Quiescente / non definito",
    "303120": "Zona di attenzione per Instabilità di versante Inattiva / crollo o ribaltamento",
    "303220": "Zona di attenzione per Instabilità di versante Inattiva / scorrimento",
    "303320": "Zona di attenzione per Instabilità di versante Inattiva / colata",
    "303420": "Zona di attenzione per Instabilità di versante Inattiva / complessa",
    "303520": "Zona di attenzione per Instabilità di versante Inattiva / non definito",
    "304120": "Zona di attenzione per Instabilità di versante Non definita / crollo o ribaltamento",
    "304220": "Zona di attenzione per Instabilità di versante Non definita / scorrimento",
    "304320": "Zona di attenzione per Instabilità di versante Non definita / colata",
    "304420": "Zona di attenzione per Instabilità di versante Non definita / complessa",
    "304520": "Zona di attenzione per Instabilità di versante Non definita / non definito",
    "305020": "Zona di attenzione per liquefazione",
    "3060": "Zona di attenzione per faglie attive e capaci",
    "3070": "Zona di Attenzione per sovrapposizione di instabilità differenti",
    "3080": "Zona di Attenzione per cedimenti differenziali/crollo di cavità/sinkhole"
}

# Lista dei campi da eliminare
fields_to_delete = ["FA", "FV", "Ft", "FH0105", "FH0510", "FPGA", "SPETTRI", "LIVELLO", "FRT", "FRR", "IL", "DISL", "FPGA"]

# Funzione per normalizzare i codici
def normalize_code(code, length=None):
    if code is None:
        return ''
    code = str(code).strip().upper()
    code = code.lstrip('0')  # Rimuove eventuali zeri iniziali
    if length:
        code = code[:length]
    return code

# Funzione per aggiungere campi agli shapefile
def add_fields(shapefile, fields_to_add):
    print("\nAggiunta campi a {}".format(shapefile))
    existing_fields = [field.name.upper() for field in arcpy.ListFields(shapefile)]
    for field in fields_to_add:
        field_name = field[0].upper()
        field_type = field[1]
        field_length = field[2] if len(field) > 2 else ""
        if field_name not in existing_fields:
            arcpy.AddField_management(shapefile, field[0], field_type, "", "", field_length)
            print("Campo '{}' aggiunto a {}".format(field[0], shapefile))
        else:
            print("Campo '{}' già presente in {}".format(field[0], shapefile))

# Funzione per eliminare campi specificati dagli shapefile
def delete_fields(shapefile, fields_to_delete):
    existing_fields = [field.name for field in arcpy.ListFields(shapefile)]
    for field in fields_to_delete:
        if field in existing_fields:
            arcpy.DeleteField_management(shapefile, field)
            print("Campo '{}' eliminato da {}".format(field, shapefile))
        else:
            print("Campo '{}' non trovato in {}".format(field, shapefile))

# Funzione per popolare il campo Comune
def populate_comune(shapefile):
    print("Popolamento campo 'Comune' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, ["Comune"]) as cursor:
        for row in cursor:
            row[0] = COMUNE_NOME
            cursor.updateRow(row)
    print("Campo 'Comune' popolato in {}".format(shapefile))

# Funzione per popolare il campo DESCR utilizzando un dizionario
def populate_descr(shapefile, code_field, descr_dict, code_length=None):
    print("Popolamento campo 'DESCR' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, [code_field, "DESCR"]) as cursor:
        for row in cursor:
            code = normalize_code(row[0], code_length)
            if code in descr_dict:
                row[1] = descr_dict[code]
            else:
                row[1] = "Tipo {}".format(code)
                print("Codice '{}' non trovato nel dizionario".format(code))
            cursor.updateRow(row)
    print("Campo 'DESCR' popolato in {}".format(shapefile))

# Funzione per popolare il campo URL
def populate_url_ms1(shapefile, code_field, code_length=None):
    print("Popolamento campo 'URL' in {}".format(shapefile))
    with arcpy.da.UpdateCursor(shapefile, [code_field, "URL"]) as cursor:
        for row in cursor:
            code = normalize_code(row[0], code_length)
            if code:
                # Costruisci l'URL seguendo le regole specificate e cambia .pdf a .jpg
                url = u"https://www.cartografia.servizirl.it/download/sismica/{}_{}.jpg".format(COMUNE_CODICE, code)
                row[1] = url
                cursor.updateRow(row)
            else:
                print("Codice '{}' non valido per URL".format(row[0]))
    print("Campo 'URL' popolato in {}".format(shapefile))

# Funzione per elaborare MS1
def process_ms1():
    print("\n--- Inizio elaborazione MS1 per il comune di {} ---".format(COMUNE_NOME))
    
    # Imposta l'ambiente di lavoro alla cartella MS1
    arcpy.env.workspace = WORKSPACE_MS1
    
    # Lista degli shapefile da elaborare
    shapefiles = ["Stab.shp", "Instab.shp"]
    
    for shapefile_name in shapefiles:
        shapefile = os.path.join(WORKSPACE_MS1, shapefile_name)
        if arcpy.Exists(shapefile):
            print("\nElaborazione dello shapefile: {}".format(shapefile))
            
            # Definisci i campi da aggiungere
            fields_to_add = [("Comune", "TEXT", 50), ("DESCR", "TEXT", 255), ("URL", "TEXT", 255)]
            add_fields(shapefile, fields_to_add)
            
            # Popola il campo Comune
            populate_comune(shapefile)
            
            # Determina il tipo di shapefile e setta i parametri appropriati
            if shapefile_name.lower() == "stab.shp":
                code_field = "Tipo_z"         # Campo codice per Stab.shp
                descr_dict = descr_dict_stab
                code_length = 4                # Considera solo i primi 4 caratteri
            elif shapefile_name.lower() == "instab.shp":
                code_field = "Tipo_i"         # Campo codice per Instab.shp
                descr_dict = descr_dict_instab
                code_length = 6                # Considera solo i primi 6 caratteri
            else:
                print("Shapefile '{}' non riconosciuto per la popolazione di DESCR e URL".format(shapefile_name))
                continue
            
            # Popola il campo DESCR
            populate_descr(shapefile, code_field, descr_dict, code_length)
            
            # Popola il campo URL
            populate_url_ms1(shapefile, code_field, code_length)
            
            # Elimina i campi specificati
            delete_fields(shapefile, fields_to_delete)
        else:
            print("Shapefile '{}' non trovato".format(shapefile_name))
    
    print("\n--- Elaborazione completata per MS1 del comune di {} ---".format(COMUNE_NOME))

# Funzione principale
def main():
    print("--- Inizio elaborazione per il comune di {} ---".format(COMUNE_NOME))
    process_ms1()
    print("--- Elaborazione completata per il comune di {} ---".format(COMUNE_NOME))

# Esegui la funzione principale
if __name__ == "__main__":
    main()
