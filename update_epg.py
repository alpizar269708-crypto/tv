import gzip
import urllib.request
import re
import xml.etree.ElementTree as ET

EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
]

M3U_FILE = "lista.m3u"
OUTPUT_EPG = "epg.xml"

def obtener_criterios():
    ids = set()
    nombres = set()
    try:
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("#EXTINF"):
                    # Extraer ID
                    match_id = re.search(r'tvg-id="([^"]+)"', line)
                    if match_id and match_id.group(1):
                        ids.add(match_id.group(1).strip().lower())
                    
                    # Extraer Nombre
                    nombre = line.split(',')[-1].strip().lower()
                    if nombre:
                        nombres.add(nombre)
    except Exception as e:
        print(f"Error leyendo m3u: {e}")
    return ids, nombres

def procesar_epgs():
    ids_req, nombres_req = obtener_criterios()
    if not ids_req and not nombres_req:
        print("No se encontraron canales en lista.m3u")
        return

    canales_agregados = set()
    
    with open(OUTPUT_EPG, 'w', encoding='utf-8') as out_f:
        out_f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

        for url in EPG_SOURCES:
            print(f"Descargando {url}...")
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with urllib.request.urlopen(req) as response:
                    with gzip.GzipFile(fileobj=response) as uncompressed:
                        context = ET.iterparse(uncompressed, events=("end",))
                        for event, elem in context:
                            if elem.tag == 'channel':
                                cid = elem.get('id')
                                cid_check = cid.strip().lower() if cid else ""
                                
                                dname = elem.find('display-name')
                                name_check = dname.text.strip().lower() if dname is not None and dname.text else ""

                                if cid_check in ids_req or name_check in nombres_req:
                                    if cid not in canales_agregados:
                                        out_f.write(ET.tostring(elem, encoding='unicode'))
                                        canales_agregados.add(cid)
                                elem.clear()
                                
                            elif elem.tag == 'programme':
                                if elem.get('channel') in canales_agregados:
                                    out_f.write(ET.tostring(elem, encoding='unicode'))
                                elem.clear()
            except Exception as e:
                print(f"Error procesando {url}: {e}")

        out_f.write('</tv>\n')

if __name__ == "__main__":
    procesar_epgs()
