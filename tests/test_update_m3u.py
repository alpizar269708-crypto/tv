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
        self.assertEqual(
            update_m3u.identificar_canal(
                '#EXTINF:-1 tvg-id="LasEstrellasLatinAmerica.mx",Las Estrellas Latin America'
            ),
            "las_estrellas",
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
        self.assertIsNone(
            update_m3u.identificar_canal(
                '#EXTINF:-1 tvg-id="MariaVision.it@SD",María Visión Italia'
            )
        )
        self.assertIsNone(
            update_m3u.identificar_canal('#EXTINF:-1,María Visión Italia')
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
            '#EXTINF:-1 tvg-id="MariaVision.it",María Visión Italia\n'
            "https://1601580044.rsc.cdn77.org/live/_jcn_/amlst:Italiasette/playlist.m3u8\n"
        )
        candidates = update_m3u.obtener_candidatos_prioritarios({source: content})
        self.assertTrue(
            all("unknown.example" not in item.url for items in candidates.values() for item in items)
        )
        self.assertGreaterEqual(len(candidates["las_estrellas"]), 5)
        self.assertGreaterEqual(len(candidates["maria_vision"]), 2)
        self.assertTrue(
            any("15.204.246.24:8080/LasEstrellasHD/index.m3u8" in item.url
                for item in candidates["las_estrellas"])
        )

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

        fake_probe = unittest.mock.Mock(returncode=0, stdout="h264,video\n", stderr="")
        with (
            patch.object(update_m3u.urllib.request, "urlopen", side_effect=fake_urlopen),
            patch.object(update_m3u.shutil, "which", return_value="/usr/bin/ffprobe"),
            patch.object(update_m3u.subprocess, "run", return_value=fake_probe),
        ):
            result = update_m3u.validar_hls("https://example.com/stream.m3u8")
        self.assertTrue(result.ok)
        self.assertIn("Video detectado", result.detail)

    def test_validador_rechaza_playlist_sin_video_real(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/vnd.apple.mpegurl"}

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
                return FakeResponse(b"#EXTM3U\n#EXTINF:6.0,\nsegment.ts\n", url)
            if url.endswith("/segment.ts"):
                return FakeResponse(b"valid-segment-bytes", url)
            raise AssertionError(url)

        fake_probe = unittest.mock.Mock(returncode=0, stdout="aac,audio\n", stderr="")
        with (
            patch.object(update_m3u.urllib.request, "urlopen", side_effect=fake_urlopen),
            patch.object(update_m3u.shutil, "which", return_value="/usr/bin/ffprobe"),
            patch.object(update_m3u.subprocess, "run", return_value=fake_probe),
        ):
            result = update_m3u.validar_hls("https://example.com/stream.m3u8")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "no_video")

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

    def test_promueve_el_primer_respaldo_con_video_y_publica_una_sola_entrada(self):
        first = "https://a.example/main.m3u8"
        backup_video = "https://a.example/backup-video.m3u8"
        backup_later = "https://a.example/another-video.m3u8"
        maria_main = "https://b.example/main.m3u8"
        maria_backup = "https://b.example/backup.m3u8"
        candidates = {
            "las_estrellas": [
                update_m3u.Candidate("las_estrellas", first, "principal"),
                update_m3u.Candidate("las_estrellas", backup_video, "respaldo 1"),
                update_m3u.Candidate("las_estrellas", backup_later, "respaldo 2"),
            ],
            "maria_vision": [
                update_m3u.Candidate("maria_vision", maria_main, "principal"),
                update_m3u.Candidate("maria_vision", maria_backup, "respaldo 1"),
            ],
        }
        outcomes = {
            first: False,
            backup_video: True,
            backup_later: True,
            maria_main: False,
            maria_backup: True,
        }

        def probe(url):
            return update_m3u.ProbeResult(
                outcomes[url],
                "ok" if outcomes[url] else "no_video",
                "video detectado" if outcomes[url] else "sin pista de video",
            )

        current = {"las_estrellas": first, "maria_vision": maria_main}
        block, summary = update_m3u.construir_bloque_prioritario(
            candidates, actuales=current, probe=probe
        )
        self.assertEqual(len(block), 5)
        self.assertEqual(
            [url for _, url in block],
            [backup_video, first, backup_later, maria_backup, maria_main],
        )
        self.assertEqual(summary["las_estrellas"]["video"], 2)
        self.assertEqual(summary["maria_vision"]["video"], 1)
        self.assertEqual(summary["las_estrellas"]["estado"], "PROMOVIDO")
        self.assertEqual(summary["maria_vision"]["estado"], "PROMOVIDO")
        self.assertNotIn("respaldo", block[0][0].lower())
        self.assertIn("Respaldo 1 - sin verificar", block[1][0])
        self.assertIn("Respaldo 2 - video confirmado", block[2][0])
        self.assertIn("Respaldo 1 - sin verificar", block[4][0])

    def test_conserva_la_ultima_url_si_ninguna_variante_tiene_video(self):
        current = "https://a.example/last-known.m3u8"
        candidates = {
            "las_estrellas": [
                update_m3u.Candidate("las_estrellas", current, "principal"),
                update_m3u.Candidate("las_estrellas", "https://a.example/dead.m3u8", "respaldo"),
            ],
            "maria_vision": [
                update_m3u.Candidate("maria_vision", "https://b.example/dead.m3u8", "respaldo"),
            ],
        }

        def no_video(url):
            return update_m3u.ProbeResult(False, "no_video", "sin video")

        block, summary = update_m3u.construir_bloque_prioritario(
            candidates,
            actuales={"las_estrellas": current, "maria_vision": "https://b.example/previous.m3u8"},
            probe=no_video,
        )
        self.assertEqual(len(block), 4)
        self.assertEqual(block[0][1], current)
        self.assertEqual(block[2][1], "https://b.example/previous.m3u8")
        self.assertIn("Respaldo", block[1][0])
        self.assertIn("Respaldo", block[3][0])
        self.assertFalse(summary["las_estrellas"]["verificada"])
        self.assertEqual(summary["las_estrellas"]["estado"], "CONSERVA ÚLTIMA URL")

    def test_recupera_respaldos_publicados_aunque_ya_no_aparezcan_en_indices(self):
        content = (
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="LasEstrellas.mx@SD",Las Estrellas\n'
            "https://15.204.246.24:8080/LasEstrellasHD/index.m3u8\n"
            '#EXTINF:-1 tvg-id="LasEstrellas.mx@SD" group-title="Respaldos",Las Estrellas (Respaldo 1 - video confirmado)\n'
            "https://190.93.224.42/CANAL-LAS-ESTRELLAS/index.m3u8\n"
        )
        with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
            respaldos = update_m3u.obtener_respaldos_prioritarios_existentes("lista.m3u")
        self.assertEqual(
            respaldos["las_estrellas"],
            ["https://190.93.224.42/CANAL-LAS-ESTRELLAS/index.m3u8"],
        )

    def test_obtiene_url_actual_de_una_sola_entrada_por_canal(self):
        content = (
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="LasEstrellas.mx@SD",Las Estrellas\n'
            "https://a.example/main.m3u8\n"
            '#EXTINF:-1 tvg-id="LasEstrellas.mx@SD",Las Estrellas (respaldo 1)\n'
            "https://a.example/backup.m3u8\n"
            '#EXTINF:-1 tvg-id="MariaVision.mx@SD",María Visión\n'
            "https://b.example/main.m3u8\n"
        )
        with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
            actuales = update_m3u.obtener_canales_prioritarios_existentes("lista.m3u")
        self.assertEqual(actuales["las_estrellas"], "https://a.example/main.m3u8")
        self.assertEqual(actuales["maria_vision"], "https://b.example/main.m3u8")


if __name__ == "__main__":
    unittest.main()
