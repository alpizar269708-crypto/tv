import urllib.request
import re

URL_MX = "https://iptv-org.github.io/iptv/countries/mx.m3u"
URL_SPA = "https://iptv-org.github.io/iptv/languages/spa.m3u"
OUTPUT_FILE = "lista.m3u"
MAX_CHANNELS = 300

ESTADOS_EXCLUIDOS = ['monterrey', 'guadalajara', 'jalisco', 'nuevo leon', 'puebla', 'veracruz', 'yucatan', 'chiapas', 'guanajuato', 'michoacan', 'sonora', 'sinaloa', 'chihuahua']
KEYWORDS_PREFERIDAS = ['cine', 'movie', 'film', 'pelicul', 'serie', 'music', 'mtv', 'kids', 'infantil', 'cartoon', 'docu', 'sport', 'deport', 'espn', 'fox', 'entret', 'comedy', 'historia', 'cultura', 'animal']

def limpiar_nombre(nombre):
    return re.sub(r'(?i)\s*[\[\(]?(1080p|720p|4k|hd|fhd|sd|hq|hevc)[\]\)]?', '', nombre).strip()

def leer_m3u(url):
    canales = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            lines = response.read().decode('utf-8').splitlines()
            
        extinf = ""
        for line in lines:
            if line.startswith("#EXTINF"): extinf = line
            elif line.startswith("http") and extinf:
                canales.append((extinf, line))
                extinf = ""
    except Exception as e: 
        print(f"Error leyendo {url}: {e}")
    return canales

def procesar():
    lista_final = []
    urls_agregadas = set()

    mx = leer_m3u(URL_MX)
    for extinf, url in mx:
        if len(lista_final) >= MAX_CHANNELS: break
        if url in urls_agregadas: continue
        
        nombre_lower = extinf.lower()
        if 'relig' in nombre_lower and 'mariavision' not in nombre_lower and 'maría visión' not in nombre_lower: continue
        if any(est in nombre_lower for est in ESTADOS_EXCLUIDOS): continue
            
        lista_final.append((extinf, url))
        urls_agregadas.add(url)

    spa = leer_m3u(URL_SPA)
    
    # Relleno VIP (Cine, deportes, etc)
    for extinf, url in spa:
        if len(lista_final) >= MAX_CHANNELS: break
        if url in urls_agregadas: continue
        if any(kw in extinf.lower() for kw in KEYWORDS_PREFERIDAS):
            lista_final.append((extinf, url))
            urls_agregadas.add(url)

    # Relleno general si aún faltan
    for extinf, url in spa:
        if len(lista_final) >= MAX_CHANNELS: break
        if url in urls_agregadas: continue
        nombre_lower = extinf.lower()
        if 'relig' in nombre_lower or 'news' in nombre_lower or 'noticias' in nombre_lower: continue
        lista_final.append((extinf, url))
        urls_agregadas.add(url)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for extinf, url in lista_final:
            nombre = re.search(r',(.*)$', extinf).group(1) if re.search(r',(.*)$', extinf) else ""
            nombre_limpio = limpiar_nombre(nombre)
            
            tvg_id_match = re.search(r'tvg-id="([^"]+)"', extinf)
            tid = tvg_id_match.group(1) if tvg_id_match and tvg_id_match.group(1) else nombre_limpio.replace(" ", "")
            
            tvg_logo = re.search(r'tvg-logo="([^"]+)"', extinf)
            logo = tvg_logo.group(1) if tvg_logo else ""
            
            f.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-logo="{logo}",{nombre_limpio}\n{url}\n')

if __name__ == "__main__":
    procesar()
