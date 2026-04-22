import requests
import re
import datetime

URL_MEXICO = "https://iptv-org.github.io/iptv/countries/mx.m3u"
URL_ESPANOL = "https://iptv-org.github.io/iptv/languages/spa.m3u"
ARCHIVO_DESTINO = "lista.m3u"
URL_TU_EPG = "https://raw.githubusercontent.com/alpizar269708-crypto/tv/main/guia.xml"

# Diccionario Maestro para forzar vínculo con la EPG mundial
MAPEO_MAESTRO = {
    "las estrellas": "LasEstrellas.mx", "canal 5": "Canal5.mx", "azteca 7": "Azteca7.mx",
    "azteca uno": "AztecaUno.mx", "adn 40": "ADN40.mx", "a mas": "APlus.mx",
    "canal once": "CanalOnce.mx", "canal 22": "Canal22.mx", "foro tv": "ForoTV.mx",
    "nu9ve": "Canal9.mx", "multimedios": "Multimedios.mx", "imagen": "ImagenTelevision.mx",
    "maria vision": "MariaVision.mx", "enlace": "Enlace.us", "ewtn": "EWTN.us",
    "telemundo": "Telemundo.us", "univision": "Univision.us", "cine canal": "CineCanal.cl",
    "fox sports": "FoxSports.mx", "espn": "ESPN.mx", "hbo": "HBO.us"
}

def limpiar_nombre(n):
    return re.sub(r"\s*\(.*?\)|\s*\[.*?\]|\s*\|.*$|\s*\.(mx|es|ar|tv)|\s*[-:]\s*\d+p|\b(HD|FHD|SD|4K|RAW)\b", "", n, flags=re.IGNORECASE).strip()

def procesar_tag(tag):
    if "," not in tag: return tag
    partes = tag.rsplit(",", 1)
    metadata, nombre_org = partes[0], partes[1].strip()
    nombre_l = limpiar_nombre(nombre_org)
    
    id_f = ""
    for clave, id_real in MAPEO_MAESTRO.items():
        if clave in nombre_l.lower():
            id_f = id_real
            break
    
    if not id_f:
        m = re.search(r'tvg-id="([^"]+)"', metadata)
        id_f = m.group(1) if m else re.sub(r'[^a-zA-Z0-9]', '', nombre_l) + ".tv"

    return f'#EXTINF:-1 tvg-id="{id_f}" tvg-name="{nombre_l}",{nombre_l}'

def generar():
    try:
        r1 = requests.get(URL_MEXICO, timeout=30).text
        r2 = requests.get(URL_ESPANOL, timeout=30).text
        lineas = (r1 + "\n" + r2).splitlines()
        lista, urls = [], set()
        for i in range(len(lineas)):
            if lineas[i].startswith("#EXTINF") and i+1 < len(lineas) and lineas[i+1].startswith("http"):
                u = lineas[i+1].strip()
                if u not in urls:
                    lista.append((procesar_tag(lineas[i]), u))
                    urls.add(u)
        
        with open(ARCHIVO_DESTINO, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{URL_TU_EPG}" url-tvg="{URL_TU_EPG}"\n')
            f.write(f'# Actualizado: {datetime.datetime.now()}\n')
            for t, u in lista[:250]: f.write(f"{t}\n{u}\n")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__": generar()
