#!/usr/bin/env python3
"""Build lista.m3u, promote a playable main URL and retain labelled backups.

Every run probes the published main URL, previously published backups and
configured/discovered alternatives. Only a candidate confirmed by ffprobe
becomes the main entry; all other candidates remain as labelled backups.
If nothing has confirmed video, the last saved main URL is preserved.
"""

from dataclasses import dataclass
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

URL_MX = "https://iptv-org.github.io/iptv/countries/mx.m3u"
URL_SPA = "https://iptv-org.github.io/iptv/languages/spa.m3u"
# A second public M3U index is consulted only for the two priority channels.
URL_MX_EXTRA = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_mexico.m3u8"
M3U_SOURCES = (URL_MX, URL_SPA, URL_MX_EXTRA)
OUTPUT_FILE = "lista.m3u"
MAX_CHANNELS = 300
SOURCE_TIMEOUT = 20
PROBE_TIMEOUT = 12
VIDEO_PROBE_TIMEOUT = 22
USER_AGENT = "Mozilla/5.0 (compatible; TVPlaylistValidator/3.0)"
MAX_MANIFEST_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 12 * 1024 * 1024

ESTADOS_EXCLUIDOS = [
    "monterrey", "guadalajara", "jalisco", "nuevo leon", "puebla",
    "veracruz", "yucatan", "chiapas", "guanajuato", "michoacan",
    "sonora", "sinaloa", "chihuahua",
]
KEYWORDS_PREFERIDAS = [
    "cine", "movie", "film", "pelicul", "serie", "music", "mtv",
    "kids", "infantil", "cartoon", "docu", "sport", "deport", "espn",
    "fox", "entret", "comedy", "historia", "cultura", "animal",
]

# Only known CDN endpoints for the exact channels are accepted from the M3U
# indexes. This prevents an arbitrary playlist from injecting unrelated or
# short-lived restream URLs into the permanent playlist.
PRIORITY_CHANNELS = {
    "las_estrellas": {
        "name": "Las Estrellas",
        "tvg_id": "LasEstrellas.mx@SD",
        "logo": "https://i.imgur.com/g5ShxZ7.png",
        "official_page": "https://www.lasestrellas.tv/las-estrellas-en-vivo-livestream",
        # CDN and public HLS origins catalogued for Las Estrellas / its
        # Latin America feed. Keep each exact host allowlisted; never accept
        # arbitrary .m3u8 URLs from unrelated HTML or ads.
        "allowed_hosts": {
            "channel01-onlymex.akamaized.net",
            "15.204.246.24",
            "190.93.224.42",
            "209.14.115.253",
        },
        "fallbacks": [
            "https://channel01-onlymex.akamaized.net/hls/live/2022749/event01/index.m3u8",
            "https://channel01-onlymex.akamaized.net/hls/live/2022749/event01/index_6.m3u8",
            "http://15.204.246.24:8080/LasEstrellasHD/index.m3u8",
            "http://190.93.224.42/CANAL-LAS-ESTRELLAS/index.m3u8",
            "http://209.14.115.253:8081/LAS-ESTRELLAS/index.m3u8",
        ],
    },
    "maria_vision": {
        "name": "María Visión",
        "tvg_id": "MariaVision.mx@SD",
        "logo": "https://i.imgur.com/GylOPxE.png",
        "official_page": "https://www.mariavision.com/livemvmx",
        "allowed_hosts": {"1601580044.rsc.cdn77.org"},
        "fallbacks": [
            "https://1601580044.rsc.cdn77.org/live/_jcn_/amlst:Mariavision/master.m3u8",
            "https://1601580044.rsc.cdn77.org/live/_jcn_/amlst:Mariavision/playlist.m3u8",
        ],
    },
}


@dataclass(frozen=True)
class Candidate:
    channel_key: str
    url: str
    source: str


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    status: str
    detail: str


def normalizar(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(char for char in texto if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def limpiar_nombre(nombre):
    return re.sub(
        r"(?i)\s*[\[\(]?(1080p|720p|4k|hd|fhd|sd|hq|hevc)[\]\)]?",
        "",
        nombre,
    ).strip()


def extinf_nombre(extinf):
    match = re.search(r",(.*)$", extinf)
    return match.group(1).strip() if match else ""


def identificar_canal(extinf):
    """Return a priority key only for the exact linear TV channels."""
    name = normalizar(extinf_nombre(extinf))
    tvg_id_match = re.search(r'(?i)tvg-id="([^"]+)"', extinf)
    tvg_id = normalizar(tvg_id_match.group(1)) if tvg_id_match else ""
    combined = name + tvg_id

    if "lasestrellas" in combined:
        return "las_estrellas"

    # Exclude other country/network variants (for example Italia Sette),
    # plus radio/capilla feeds. The requested entry is María Visión México.
    regional_or_non_tv = (
        "radio", "capilla", "chapel", "italia", "italy", "italiasette",
        "mariavisionit", "mariavisionusa", "sevilla", "india", "polonia",
        "polska", "medjugorje", "medju", "fatima", "carloacutis",
    )
    if "mariavision" in combined and not any(
        word in name or word in tvg_id for word in regional_or_non_tv
    ):
        return "maria_vision"
    return None


def parsear_m3u(texto):
    canales = []
    extinf = None
    for raw_line in texto.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if line.startswith("#EXTINF"):
            extinf = line
        elif not line or line.startswith("#"):
            continue
        elif extinf and line.lower().startswith(("http://", "https://")):
            canales.append((extinf, line))
            extinf = None
    return canales


def descargar_texto(url, timeout=SOURCE_TIMEOUT, max_bytes=MAX_SOURCE_BYTES):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; TVPlaylistUpdater/2.0)",
            "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes)
    return data.decode("utf-8-sig", errors="replace")


def _leer_respuesta(url, byte_range=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TVPlaylistValidator/2.0)",
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
        "Connection": "close",
    }
    if byte_range:
        headers["Range"] = byte_range
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
            status = getattr(response, "status", None) or response.getcode()
            data = response.read(4096 if byte_range else MAX_MANIFEST_BYTES)
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            return status, data, final_url, content_type, ""
    except urllib.error.HTTPError as error:
        return error.code, b"", url, "", str(error)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, b"", url, "", str(error)


def _es_html(data, content_type):
    sample = data[:256].lstrip().lower()
    return "text/html" in (content_type or "").lower() or sample.startswith(
        (b"<!doctype html", b"<html", b"<head", b"<body")
    )


def _validar_hls(url, depth=0):
    if depth > 2:
        return ProbeResult(False, "invalid", "Demasiadas redirecciones entre playlists")

    status, data, final_url, content_type, error = _leer_respuesta(url)
    if status not in (200, 206):
        if status == 403 or status == 451:
            detail = "HTTP %s: posible restricción geográfica o de acceso" % status
        elif status == 429:
            detail = "HTTP 429: límite temporal del servidor"
        elif status == 0:
            detail = "No se pudo conectar: %s" % (error or "error de red")
        else:
            detail = "HTTP %s: %s" % (status, error or "respuesta no válida")
        return ProbeResult(False, "unverified", detail)

    if _es_html(data, content_type):
        return ProbeResult(False, "invalid", "El servidor devolvió HTML, no una playlist HLS")

    text = data.decode("utf-8-sig", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U":
        return ProbeResult(False, "invalid", "La respuesta no contiene una cabecera #EXTM3U")

    # A master playlist points to one or more renditions. Verify one rendition
    # recursively before accepting the master.
    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for child in lines[index + 1 :]:
                if not child.startswith("#"):
                    return _validar_hls(urllib.parse.urljoin(final_url, child), depth + 1)
            return ProbeResult(False, "invalid", "Playlist maestra sin variante de video")

    # A media playlist is only marked playable after its first media segment
    # can also be fetched. A 200 HTML error page is not accepted as a segment.
    segment = next((line for line in lines if not line.startswith("#")), None)
    if not segment:
        return ProbeResult(False, "invalid", "Playlist sin segmentos multimedia")

    segment_url = urllib.parse.urljoin(final_url, segment)
    seg_status, seg_data, _, seg_type, seg_error = _leer_respuesta(
        segment_url, byte_range="bytes=0-1023"
    )
    if seg_status not in (200, 206) or not seg_data or _es_html(seg_data, seg_type):
        return ProbeResult(
            False,
            "unverified",
            "Manifesto HLS válido, pero no se pudo leer el primer segmento: %s"
            % (seg_error or "HTTP %s" % seg_status),
        )

    return ProbeResult(True, "ok", "Manifesto HLS y primer segmento accesibles")


def validar_hls(url):
    """Require both an accessible HLS segment and an actual video stream."""
    basic = _validar_hls(url)
    if not basic.ok:
        return basic

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return ProbeResult(False, "validator_missing", "ffprobe no está instalado; no se confirma video")

    command = [
        ffprobe,
        "-v", "error",
        "-rw_timeout", "12000000",
        "-user_agent", USER_AGENT,
        "-i", url,
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type,codec_name",
        "-of", "csv=p=0",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=VIDEO_PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(False, "video_timeout", "ffprobe agotó el tiempo al buscar video")
    except OSError as error:
        return ProbeResult(False, "video_error", "No se pudo ejecutar ffprobe: %s" % error)

    output = (result.stdout or "").strip()
    if result.returncode == 0 and output and "video" in output.lower():
        return ProbeResult(True, "ok", "Video detectado por ffprobe: %s" % output.replace("\n", ", "))
    detail = (result.stderr or output or "No se encontró una pista de video").strip()
    return ProbeResult(False, "no_video", "La playlist/segmento responde, pero no contiene video: %s" % detail[:240])


def obtener_canales_prioritarios_existentes(path=OUTPUT_FILE):
    """Read the currently published main URL so it can be tested first and preserved on outage."""
    actuales = {}
    try:
        with open(path, "r", encoding="utf-8") as source:
            for extinf, url in parsear_m3u(source.read()):
                key = identificar_canal(extinf)
                if key and key not in actuales:
                    actuales[key] = url
    except FileNotFoundError:
        pass
    return actuales


def obtener_respaldos_prioritarios_existentes(path=OUTPUT_FILE):
    """Keep previously published backups available even if an index drops them."""
    respaldos = {key: [] for key in PRIORITY_CHANNELS}
    vistos = {key: set() for key in PRIORITY_CHANNELS}
    try:
        with open(path, "r", encoding="utf-8") as source:
            for extinf, url in parsear_m3u(source.read()):
                key = identificar_canal(extinf)
                nombre = normalizar(extinf_nombre(extinf))
                if key and "respaldo" in nombre and url not in vistos[key]:
                    vistos[key].add(url)
                    respaldos[key].append(url)
    except FileNotFoundError:
        pass
    return respaldos


def obtener_candidatos_prioritarios(textos_por_fuente, actuales=None):
    candidatos = {key: [] for key in PRIORITY_CHANNELS}
    vistos = {key: set() for key in PRIORITY_CHANNELS}

    def agregar(key, url, source):
        if key not in PRIORITY_CHANNELS:
            return
        # Do not let a generic "María Visión" label disguise a different feed.
        normalized_url = normalizar(url)
        if key == "maria_vision" and any(
            marker in normalized_url for marker in ("italiasette", "mariavisionitalia", "mariavisionit")
        ):
            return
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        config = PRIORITY_CHANNELS[key]
        if parsed.scheme not in ("http", "https") or host not in config["allowed_hosts"]:
            return
        if not re.search(r"\.m3u8?(?:$|\?)", parsed.path, flags=re.IGNORECASE):
            return
        if url in vistos[key]:
            return
        vistos[key].add(url)
        candidatos[key].append(Candidate(key, url, source))

    # Test the previously published main URL first. If it still contains video,
    # keep it stable; otherwise a working backup will be promoted automatically.
    for key, url in (actuales or {}).items():
        agregar(key, url, "URL principal publicada")

    # Previously published backup entries survive temporary upstream index drops.
    for key, urls in obtener_respaldos_prioritarios_existentes().items():
        for url in urls:
            agregar(key, url, "respaldo publicado anteriormente")

    # Explicit backups remain in code so transient upstream index changes never
    # remove a known option for either requested channel.
    for key, config in PRIORITY_CHANNELS.items():
        for url in config["fallbacks"]:
            agregar(key, url, "respaldo configurado")

    # Discover additional renditions in more than one public M3U index, while
    # enforcing the per-channel CDN allowlist above.
    for source, texto in textos_por_fuente.items():
        for extinf, url in parsear_m3u(texto):
            key = identificar_canal(extinf)
            if key:
                agregar(key, url, source)

    return candidatos


def crear_extinf_prioritario(key):
    config = PRIORITY_CHANNELS[key]
    return (
        '#EXTINF:-1 tvg-id="%s" tvg-logo="%s" group-title="Canales prioritarios",%s'
        % (config["tvg_id"], config["logo"], config["name"])
    )


def crear_extinf_respaldo(key, numero, verificado):
    """Create a clearly labelled backup entry after the canonical channel."""
    config = PRIORITY_CHANNELS[key]
    estado = "video confirmado" if verificado else "sin verificar"
    nombre = "%s (Respaldo %d - %s)" % (config["name"], numero, estado)
    return (
        '#EXTINF:-1 tvg-id="%s" tvg-logo="%s" group-title="Respaldos",%s'
        % (config["tvg_id"], config["logo"], nombre)
    )


def construir_bloque_prioritario(candidatos, actuales=None, probe=validar_hls):
    """Promote the first candidate with real video and retain the rest as backups."""
    bloque = []
    resumen = {}
    actuales = actuales or {}

    for key, config in PRIORITY_CHANNELS.items():
        opciones = candidatos.get(key, [])
        resultados = []
        elegido = None
        resultado_elegido = None

        # Test the current main URL first, then configured backups. Test all candidates.
        for candidate in opciones:
            result = probe(candidate.url)
            resultados.append((candidate, result))
            estado = "VIDEO" if result.ok else "SIN VIDEO"
            print("[%s] %s | %s | %s" % (estado, config["name"], candidate.url, result.detail))
            if result.ok and elegido is None:
                elegido = candidate
                resultado_elegido = result

        if elegido is not None:
            url_publicada = elegido.url
            estado_final = "PROMOVIDO" if url_publicada != actuales.get(key) else "SE MANTIENE"
            detalle = resultado_elegido.detail
        elif actuales.get(key):
            url_publicada = actuales[key]
            estado_final = "CONSERVA ÚLTIMA URL"
            detalle = "Ninguna variante confirmó video; se conserva la URL principal anterior"
        elif opciones:
            url_publicada = opciones[0].url
            estado_final = "URL INICIAL SIN VERIFICAR"
            detalle = "Ninguna variante confirmó video; se conserva el primer respaldo configurado"
        else:
            raise RuntimeError("No hay ninguna URL configurada para %s" % config["name"])

        bloque.append((crear_extinf_prioritario(key), url_publicada))
        respaldo_numero = 0
        for candidate, result in resultados:
            if candidate.url == url_publicada:
                continue
            respaldo_numero += 1
            bloque.append((crear_extinf_respaldo(key, respaldo_numero, result.ok), candidate.url))

        resumen[key] = {
            "video": sum(1 for _, result in resultados if result.ok),
            "probadas": len(resultados),
            "seleccionada": url_publicada,
            "verificada": elegido is not None,
            "respaldos": max(0, len(resultados) - (1 if resultados else 0)),
            "estado": estado_final,
        }
        print("[%s] %s | URL principal: %s | %d respaldos | %s" % (
            estado_final, config["name"], url_publicada, resumen[key]["respaldos"], detalle
        ))

    return bloque, resumen


def procesar():
    textos = {}
    canales_por_fuente = {}
    for source in M3U_SOURCES:
        try:
            texto = descargar_texto(source)
            textos[source] = texto
            canales_por_fuente[source] = parsear_m3u(texto)
            print("Fuente leída: %s (%d canales)" % (source, len(canales_por_fuente[source])))
        except Exception as error:
            canales_por_fuente[source] = []
            print("Error leyendo %s: %s" % (source, error))

    mx = canales_por_fuente.get(URL_MX, [])
    spa = canales_por_fuente.get(URL_SPA, [])
    if not mx and not spa:
        raise RuntimeError("No se pudo leer ninguna lista M3U principal; se conserva lista.m3u sin cambios")

    actuales = obtener_canales_prioritarios_existentes()
    candidatos = obtener_candidatos_prioritarios(textos, actuales)
    bloque_prioritario, resumen = construir_bloque_prioritario(candidatos, actuales)

    lista_final = list(bloque_prioritario)
    urls_agregadas = {url for _, url in lista_final}
    limite_normales = max(0, MAX_CHANNELS - len(lista_final))

    def agregar_normales(canales):
        for extinf, url in canales:
            if len(lista_final) - len(bloque_prioritario) >= limite_normales:
                break
            if url in urls_agregadas or identificar_canal(extinf):
                continue

            nombre_lower = extinf.lower()
            if "relig" in nombre_lower:
                continue
            if any(estado in nombre_lower for estado in ESTADOS_EXCLUIDOS):
                continue

            lista_final.append((extinf, url))
            urls_agregadas.add(url)

    agregar_normales(mx)

    # Preferred Spanish-language channels (movies, sports, kids, culture, etc.).
    for extinf, url in spa:
        if len(lista_final) - len(bloque_prioritario) >= limite_normales:
            break
        if url in urls_agregadas or identificar_canal(extinf):
            continue
        if any(keyword in extinf.lower() for keyword in KEYWORDS_PREFERIDAS):
            lista_final.append((extinf, url))
            urls_agregadas.add(url)

    # General Spanish-language fill if there is still room.
    for extinf, url in spa:
        if len(lista_final) - len(bloque_prioritario) >= limite_normales:
            break
        if url in urls_agregadas or identificar_canal(extinf):
            continue
        nombre_lower = extinf.lower()
        if "relig" in nombre_lower or "news" in nombre_lower or "noticias" in nombre_lower:
            continue
        lista_final.append((extinf, url))
        urls_agregadas.add(url)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as output:
        output.write("#EXTM3U\n")
        for extinf, url in lista_final:
            if extinf.startswith("#EXTINF") and identificar_canal(extinf):
                output.write(extinf + "\n" + url + "\n")
                continue

            nombre = extinf_nombre(extinf)
            nombre_limpio = limpiar_nombre(nombre)
            tvg_id_match = re.search(r'(?i)tvg-id="([^"]+)"', extinf)
            tid = tvg_id_match.group(1) if tvg_id_match and tvg_id_match.group(1) else re.sub(r"\s+", "", nombre_limpio)
            tvg_logo_match = re.search(r'(?i)tvg-logo="([^"]+)"', extinf)
            logo = tvg_logo_match.group(1) if tvg_logo_match else ""
            output.write(
                '#EXTINF:-1 tvg-id="%s" tvg-logo="%s",%s\n%s\n'
                % (tid, logo, nombre_limpio, url)
            )

    print("\nResumen de canales prioritarios:")
    for key, config in PRIORITY_CHANNELS.items():
        values = resumen[key]
        print("- %s: %d/%d con video; %s; %d respaldos." % (
            config["name"], values["video"], values["probadas"], values["estado"], values["respaldos"]
        ))
        print("  URL publicada: %s" % values["seleccionada"])
    print("Lista generada: %d entradas totales; principales y respaldos incluidos." % len(lista_final))


if __name__ == "__main__":
    try:
        procesar()
    except Exception as error:
        print("ERROR: %s" % error, file=sys.stderr)
        sys.exit(1)
