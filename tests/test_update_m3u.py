import unittest
from unittest.mock import patch

import update_m3u


class UpdateM3UTests(unittest.TestCase):
    def test_detecta_las_estrellas_sin_confundir_estrella_tv(self):
        self.assertEqual(
            update_m3u.identificar_canal(
                '#EXTINF:-1 tvg-id="LasEstrellas.mx@SD",Las Estrellas (1080p)'
            ),
            "las_estrellas",
        )
        self.assertIsNone(
            update_m3u.identificar_canal('#EXTINF:-1,Estrella TV')
        )

    def test_detecta_maria_vision_y_excluye_radio(self):
        self.assertEqual(
            update_m3u.identificar_canal(
                '#EXTINF:-1 tvg-id="MariaVision.mx@SD",María Visión México'
            ),
            "maria_vision",
        )
        self.assertIsNone(
            update_m3u.identificar_canal('#EXTINF:-1,Maria Vision Radio')
        )

    def test_parsea_m3u_y_omite_comentarios(self):
        content = (
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="x",Canal de prueba\n'
            "#EXTVLCOPT:http-user-agent=test\n"
            "https://example.com/live.m3u8\n"
        )
        self.assertEqual(
            update_m3u.parsear_m3u(content),
            [('#EXTINF:-1 tvg-id="x",Canal de prueba', "https://example.com/live.m3u8")],
        )

    def test_candidatos_solo_aceptan_hosts_permitidos(self):
        source = "https://list.example/mexico.m3u"
        content = (
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="LasEstrellas.mx",Las Estrellas\n'
            "https://unknown.example/stream.m3u8\n"
            '#EXTINF:-1 tvg-id="MariaVision.mx",María Visión México\n'
            "https://1601580044.rsc.cdn77.org/live/_jcn_/amlst:Mariavision/master.m3u8\n"
        )
        candidates = update_m3u.obtener_candidatos_prioritarios({source: content})
        self.assertTrue(
            all("unknown.example" not in item.url for items in candidates.values() for item in items)
        )
        self.assertGreaterEqual(len(candidates["las_estrellas"]), 2)
        self.assertGreaterEqual(len(candidates["maria_vision"]), 2)

    def test_validador_exige_manifest_y_segmento_hls(self):
        class FakeHeaders(dict):
            pass

        class FakeResponse:
            status = 200
            headers = FakeHeaders({"Content-Type": "application/vnd.apple.mpegurl"})

            def __init__(self, data, url):
                self.data = data
                self.url = url

            def read(self, size=-1):
                return self.data if size < 0 else self.data[:size]

            def geturl(self):
                return self.url

            def getcode(self):
                return self.status

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            url = request.full_url
            if url.endswith("/stream.m3u8"):
                return FakeResponse(
                    b"#EXTM3U\n#EXTINF:6.0,\nsegment.ts\n#EXT-X-ENDLIST\n", url
                )
            if url.endswith("/segment.ts"):
                return FakeResponse(b"fake-ts-segment-data", url)
            raise AssertionError(url)

        with patch.object(update_m3u.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = update_m3u.validar_hls("https://example.com/stream.m3u8")
        self.assertTrue(result.ok)

    def test_validador_rechaza_pagina_html(self):
        class FakeHeaders(dict):
            pass

        class FakeResponse:
            status = 200
            headers = FakeHeaders({"Content-Type": "text/html"})

            def read(self, size=-1):
                return b"<!doctype html><html>blocked</html>"

            def geturl(self):
                return "https://example.com/stream.m3u8"

            def getcode(self):
                return self.status

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(
            update_m3u.urllib.request, "urlopen", return_value=FakeResponse()
        ):
            result = update_m3u.validar_hls("https://example.com/stream.m3u8")
        self.assertFalse(result.ok)

    def test_conserva_todas_las_variantes_aunque_no_pasen_la_prueba(self):
        candidates = {
            "las_estrellas": [
                update_m3u.Candidate("las_estrellas", "https://a.example/one.m3u8", "test"),
                update_m3u.Candidate("las_estrellas", "https://a.example/two.m3u8", "test"),
            ],
            "maria_vision": [
                update_m3u.Candidate("maria_vision", "https://b.example/one.m3u8", "test"),
            ],
        }

        def no_disponible(url):
            return update_m3u.ProbeResult(False, "unverified", "prueba sin conexión")

        block, summary = update_m3u.construir_bloque_prioritario(candidates, probe=no_disponible)
        self.assertEqual(len(block), 3)
        self.assertEqual(summary["las_estrellas"]["total"], 2)
        self.assertEqual(summary["maria_vision"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
