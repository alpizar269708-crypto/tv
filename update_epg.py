import gzip
import urllib.request
import re
import xml.etree.ElementTree as ET
import unicodedata

EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
]

M3U_FILE = "lista.m3u"
OUTPUT_EPG = "epg.xml"

def normalizar(texto):
    if not texto: return ""
    # Quitar acentos
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")
    # Todo a minúsculas y quitar lo que no sea letra o número
    texto = re.sub(r'[^a-z0-9]', '', texto.lower())
    # Quitar palabras comunes que ensucian la búsqueda
    basura = ['hd', 'fhd', 'sd', 'mx', 'mexico', 'canal', 'tv']
    for b in basura:
        texto = texto.replace(b, '')
    return texto

def obtener_canales_m3u():
    canales = {} # Diccionario para búsqueda rápida {nombre_normalizado: id_original_m3u}
    try:
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("#EXTINF"):
                    # Extraer nombre visible (después de la coma)
                    nombre = line.split(',')[-1].strip()
                    nombre_norm = normalizar(nombre)
                    
                    # Extraer tvg-id si existe
                    tvg_id = ""
                    match_id = re.search(r'tvg-id="([^"]+)"', line)
                    if match_id: tvg_id = match_id.group(1)
                    
                    if nombre_norm:
                        canales[nombre_norm] = {
                            'id_m3u': tvg_id,
                            'nombre_original': nombre
                        }
    except Exception as e:
        print(f"Error leyendo m3u: {e}")
    return canales

def procesar_epgs():
    dict_m3u = obtener_canales_m3u()
    if not dict_m3u:
        print("M3U vacía o no encontrada.")
        return

    # Mapeo de IDs de la EPG que coinciden con nuestros canales
    ids_epg_encontrados = {} # {id_en_xml: info_nuestra}
    
    with open(OUTPUT_EPG, 'w', encoding='utf-8') as out_f:
        out_f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

        for url in EPG_SOURCES:
            print(f"Procesando fuente: {url}")
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    with gzip.GzipFile(fileobj=response) as uncompressed:
                        context = ET.iterparse(uncompressed, events=("end",))
                        for event, elem in context:
                            if elem.tag == 'channel':
                                epg_id = elem.get('id')
                                # Buscar por nombre del canal en la EPG
                                nombres_xml = [dn.text for dn in elem.findall('display-name') if dn.text]
                                
                                for n_xml in nombres_xml:
                                    n_xml_norm = normalizar(n_xml)
                                    if n_xml_norm in dict_m3u:
                                        # ¡Coincidencia encontrada! 
                                        # Guardamos que este ID de la EPG nos sirve
                                        ids_epg_encontrados[epg_id] = dict_m3u[n_xml_norm]
                                        # Escribimos el canal en nuestro XML
                                        out_f.write(ET.tostring(elem, encoding='unicode'))
                                        break
                                elem.clear()
                                
                            elif elem.tag == 'programme':
                                channel_id = elem.get('channel')
                                if channel_id in ids_epg_encontrados:
                                    # Este programa pertenece a un canal que ya aceptamos
                                    out_f.write(ET.tostring(elem, encoding='unicode'))
                                elem.clear()
            except Exception as e:
                print(f"Falla en {url}: {e}")

        out_f.write('</tv>\n')
    
    print(f"EPG generada. Canales vinculados: {len(ids_epg_encontrados)}")

if __name__ == "__main__":
    procesar_epgs()
