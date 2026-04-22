import requests
import re
import gzip
import xml.etree.ElementTree as ET
import os

ARCHIVO_M3U = "lista.m3u"
ARCHIVO_EPG_DESTINO = "guia.xml"
# Fuentes de todo el mundo para máxima cobertura
FUENTES = [
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
]

def filtrar():
    if not os.path.exists(ARCHIVO_M3U): return
    with open(ARCHIVO_M3U, "r", encoding="utf-8") as f:
        m3u = f.read()
        ids = set(re.findall(r'tvg-id="([^"]+)"', m3u))
        nombres = [n.lower().strip() for n in re.findall(r',(.+)$', m3u, re.MULTILINE)]

    with open(ARCHIVO_EPG_DESTINO, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="utf-8"?>\n<tv>\n')

    encontrados = set()
    for url in FUENTES:
        print(f"Descargando base de datos mundial: {url}")
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=600)
            with open("t.gz", "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024): f.write(chunk)

            with gzip.open("t.gz", 'rb') as f:
                context = ET.iterparse(f, events=('end',))
                for _, elem in context:
                    if elem.tag == 'channel':
                        cid = elem.get("id")
                        nms = [dn.text.lower() for dn in elem.findall("display-name") if dn.text]
                        if cid in ids or any(any(n in ng for ng in nms) for n in nombres):
                            if cid not in encontrados:
                                encontrados.add(cid)
                                with open(ARCHIVO_EPG_DESTINO, "a", encoding="utf-8") as o:
                                    o.write(ET.tostring(elem, encoding="unicode"))
                    elif elem.tag == 'programme' and elem.get("channel") in encontrados:
                        with open(ARCHIVO_EPG_DESTINO, "a", encoding="utf-8") as o:
                            o.write(ET.tostring(elem, encoding="unicode"))
                    elem.clear()
            os.remove("t.gz")
        except: continue

    with open(ARCHIVO_EPG_DESTINO, "a", encoding="utf-8") as o: o.write("</tv>")
    print(f"TERMINADO: {len(encontrados)} canales con programación completa.")

if __name__ == "__main__": filtrar()
