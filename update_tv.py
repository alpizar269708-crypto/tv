import urllib.request
import re

URL_MX = "https://iptv-org.github.io/iptv/countries/mx.m3u"
URL_SPA = "https://iptv-org.github.io/iptv/languages/spa.m3u"
OUTPUT_FILE = "lista.m3u"
MAX_CHANNELS = 300

# Filtros
ESTADOS_EXCLUIDOS = ['monterrey', 'guadalajara', 'jalisco', 'nuevo leon', 'puebla', 'veracruz', 'yucatan', 'chiapas', 'guanajuato', 'michoacan', 'sonora', 'sinaloa', 'chihuahua']
CATEGORIAS_DESEADAS = ['music', 'movies', 'series', 'documentary', 'culture', 'kids', 'entertainment', 'sports']
CANALES_PREMIUM_BUSCADOS = ['espn', 'fox', 'hbo', 'cinemax', 'discovery', 'national geographic']

def limpiar_nombre(nombre):
    # Elimina resoluciones y calidades del nombre visible
    nombre = re.sub(r'(?i)\s*[\[\(]?(1080p|720p|4k|hd|fhd|sd|hq|hevc)[\]\)]?', '', nombre)
    return nombre.strip()

def parse_m3u(url):
    canales = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            lines = response.read().decode('utf-8').splitlines()
    except:
        return canales

    current_extinf = ""
    for line in lines:
        if line.startswith("#EXTINF"):
            current_extinf = line
        elif line.startswith("http") and current_extinf:
            canales.append((current_extinf, line))
            current_extinf = ""
    return canales

def procesar_canales():
    canales_mx_raw = parse_m3u(URL_MX)
    canales_spa_raw = parse_m3u(URL_SPA)
    
    lista_final = []
    urls_agregadas = set()

    # 1. Procesar México
    for extinf, url in canales_mx_raw:
        if len(lista_final) >= MAX_CHANNELS: break
        if url in urls_agregadas: continue

        nombre = re.search(r',(.*)$', extinf).group(1) if re.search(r',(.*)$', extinf) else ""
        nombre_lower = nombre.lower()
        group = re.search(r'group-title="([^"]+)"', extinf)
        group_lower = group.group(1).lower() if group else ""

        # Filtro Religioso
        if 'relig' in group_lower and 'mariavision' not in nombre_lower and 'maría visión' not in nombre_lower:
            continue
        
        # Filtro Regional
        if any(estado in nombre_lower for estado in ESTADOS_EXCLUIDOS):
            continue

        # Limpiar metadatos para evitar grupos y calidades
        nombre_limpio = limpiar_nombre(nombre)
        # Se reescribe la línea EXTINF quitando group-title y poniendo el nombre limpio
        tvg_id = re.search(r'tvg-id="([^"]+)"', extinf)
        tvg_id_str = f'tvg-id="{tvg_id.group(1)}"' if tvg_id else 'tvg-id=""'
        tvg_logo = re.search(r'tvg-logo="([^"]+)"', extinf)
        tvg_logo_str = f'tvg-logo="{tvg_logo.group(1)}"' if tvg_logo else 'tvg-logo=""'
        
        nueva_extinf = f'#EXTINF:-1 {tvg_id_str} {tvg_logo_str},{nombre_limpio}'
        
        lista_final.append((nueva_extinf, url))
        urls_agregadas.add(url)

    # 2. Procesar Relleno (Premium y Categorías)
    for extinf, url in canales_spa_raw:
        if len(lista_final) >= MAX_CHANNELS: break
        if url in urls_agregadas: continue

        nombre = re.search(r',(.*)$', extinf).group(1) if re.search(r',(.*)$', extinf) else ""
        nombre_lower = nombre.lower()
        group = re.search(r'group-title="([^"]+)"', extinf)
        group_lower = group.group(1).lower() if group else ""

        es_deseado = any(cat in group_lower for cat in CATEGORIAS_DESEADAS) or any(prem in nombre_lower for prem in CANALES_PREMIUM_BUSCADOS)
        
        if es_deseado:
            nombre_limpio = limpiar_nombre(nombre)
            tvg_id = re.search(r'tvg-id="([^"]+)"', extinf)
            tvg_id_str = f'tvg-id="{tvg_id.group(1)}"' if tvg_id else 'tvg-id=""'
            tvg_logo = re.search(r'tvg-logo="([^"]+)"', extinf)
            tvg_logo_str = f'tvg-logo="{tvg_logo.group(1)}"' if tvg_logo else 'tvg-logo=""'
            
            nueva_extinf = f'#EXTINF:-1 {tvg_id_str} {tvg_logo_str},{nombre_limpio}'
            
            lista_final.append((nueva_extinf, url))
            urls_agregadas.add(url)

    # Escribir archivo M3U
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for extinf, url in lista_final:
            f.write(extinf + "\n")
            f.write(url + "\n")

if __name__ == "__main__":
    procesar_canales()
