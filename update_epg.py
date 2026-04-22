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
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")
    texto = re.sub(r'[^a-z0-9]', '', texto.lower())
    for b in ['hd', 'fhd', 'sd', 'mx', 'mexico', 'canal', 'tv']:
        texto = texto.replace(b, '')
    return texto

def obtener_canales_m3u():
    canales = {}
    try:
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("#EXTINF"):
                    nombre = line.split(',')[-1].strip()
                    nombre_norm = normalizar(nombre)
                    if nombre_norm: canales[nombre_norm] = True
    except: pass
    return canales

def procesar_epgs():
    dict_m3u = obtener_canales_m3u()
    if not dict_m3u: return

    ids_epg_encontrados = set()
    
    with open(OUTPUT_EPG, 'w', encoding='utf-8') as out_f:
        out_f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

        for url in EPG_SOURCES:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    with gzip.GzipFile(fileobj=response) as uncompressed:
                        context = ET.iterparse(uncompressed, events=("end",))
                        for event, elem in context:
                            if elem.tag == 'channel':
                                epg_id = elem.get('id')
                                nombres_xml = [dn.text for dn in elem.findall('display-name') if dn.text]
                                
                                for n_xml in nombres_xml:
                                    if normalizar(n_xml) in dict_m3u:
                                        ids_epg_encontrados.add(epg_id)
                                        out_f.write(ET.tostring(elem, encoding='unicode'))
                                        break
                                elem.clear()
                                
                            elif elem.tag == 'programme':
                                if elem.get('channel') in ids_epg_encontrados:
                                    out_f.write(ET.tostring(elem, encoding='unicode'))
                                elem.clear()
            except: pass

        out_f.write('</tv>\n')

if __name__ == "__main__":
    procesar_epgs()
