#!/usr/bin/env python3
"""Build lista.m3u and keep the two requested Mexican channels pinned.

Priority streams are checked as HLS (manifest + one media segment). A GitHub
hosted runner may be outside Mexico, so failed probes are retained as fallback
entries instead of silently removing the channels.
"""

from dataclasses import dataclass
import re
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
    """Check the HLS manifest and one media segment without downloading video."""
    return _validar_hls(url)


def obtener_candidatos_prioritarios(textos_por_fuente):
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

    # Explicit stable fallbacks guarantee both channel labels are always
    # included, even when an upstream index removes them or GitHub is geo-blocked.
    for key, config in PRIORITY_CHANNELS.items():
        for url in config["fallbacks"]:
            agregar(key, url, "respaldo fijo")

    # Discover additional renditions in more than one public M3U index, while
    # enforcing the per-channel CDN allowlist above.
    for source, texto in textos_por_fuente.items():
        for extinf, url in parsear_m3u(texto):
            key = identificar_canal(extinf)
            if key:
                agregar(key, url, source)

    return candidatos


def crear_extinf_prioritario(key, index):
    config = PRIORITY_CHANNELS[key]
    name = config["name"] if index == 0 else "%s (respaldo %d)" % (config["name"], index)
    return (
        '#EXTINF:-1 tvg-id="%s" tvg-logo="%s" group-title="Canales prioritarios",%s'
        % (config["tvg_id"], config["logo"], name)
    )


def construir_bloque_prioritario(candidatos, probe=validar_hls):
    bloque = []
    resumen = {}
    for key in PRIORITY_CHANNELS:
        resultados = []
        for candidate in candidatos.get(key, []):
            result = probe(candidate.url)
            resultados.append((candidate, result))
            estado = "OK" if result.ok else "RESPALDO"
            print(
                "[%s] %s | %s | %s"
                % (estado, PRIORITY_CHANNELS[key]["name"], candidate.url, result.detail)
            )

        # Playable options go first; failed probes are still kept so a runner
        # outside Mexico cannot accidentally erase a region-limited stream.
        resultados.sort(key=lambda item: (not item[1].ok, candidatos[key].index(item[0])))
        resumen[key] = {"ok": sum(1 for _, result in resultados if result.ok), "total": len(resultados)}
        for index, (candidate, _) in enumerate(resultados):
            bloque.append((crear_extinf_prioritario(key, index), candidate.url))

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

    candidatos = obtener_candidatos_prioritarios(textos)
    bloque_prioritario, resumen = construir_bloque_prioritario(candidatos)

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
        print("- %s: %d/%d variantes verificadas; %d incluidas" % (
            config["name"], values["ok"], values["total"], values["total"]
        ))
    print("Lista generada: %d canales totales (%d prioritarios)." % (len(lista_final), len(bloque_prioritario)))


if __name__ == "__main__":
    try:
        procesar()
    except Exception as error:
        print("ERROR: %s" % error, file=sys.stderr)
        sys.exit(1)
