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

def obtener_ids():
    ids = set()
    try:
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("#EXTINF"):
                    match = re.search(r'tvg-id="([^"]+)"', line)
                    if match and match.group(1): ids.add(match.group(1))
    except: pass
    return ids

def procesar_epgs():
    ids_requeridos = obtener_ids()
    if not ids_requeridos: return

    canales_agregados = set()
    
    with open(OUTPUT_EPG, 'w', encoding='utf-8') as out_f:
        out_f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

        for url in EPG_SOURCES:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    with gzip.GzipFile(fileobj=response) as uncompressed:
                        context = ET.iterparse(uncompressed, events=("end",))
                        for event, elem in context:
                            if elem.tag == 'channel':
                                cid = elem.get('id')
                                if cid in ids_requeridos and cid not in canales_agregados:
                                    out_f.write(ET.tostring(elem, encoding='unicode'))
                                    canales_agregados.add(cid)
                                elem.clear()
                            elif elem.tag == 'programme':
                                if elem.get('channel') in canales_agregados:
                                    out_f.write(ET.tostring(elem, encoding='unicode'))
                                elem.clear()
            except: pass

        out_f.write('</tv>\n')

if __name__ == "__main__":
    procesar_epgs()
