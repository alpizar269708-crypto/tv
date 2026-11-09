# TV – lista M3U

El workflow `1. Actualizar M3U` reconstruye `lista.m3u` y se ejecuta cada tres horas. También se puede iniciar manualmente desde **Actions**.

## Canales prioritarios

**Las Estrellas** y **María Visión** se insertan siempre al principio de `lista.m3u`, aunque una fuente pública deje de anunciarlos. El actualizador consulta más de una lista M3U, acepta únicamente hosts previamente permitidos para cada canal, comprueba el manifiesto HLS y solicita un segmento de muestra. Las variantes que responden correctamente quedan primero; las que no se pudieron comprobar se conservan como respaldo para no perder un canal por una restricción de red del runner.

La comprobación desde GitHub no garantiza la reproducción desde todos los países o proveedores. En particular, la página de Las Estrellas informa que su señal en vivo requiere cuenta de izzi y el CDN puede aplicar restricciones geográficas. Si GitHub recibe un 403, el enlace se conserva, pero no se presenta como verificado.

Páginas de señal en vivo de los canales:

- [Las Estrellas](https://www.lasestrellas.tv/las-estrellas-en-vivo-livestream)
- [María Visión México](https://www.mariavision.com/livemvmx)

## Comprobaciones locales

```bash
python -m unittest discover -s tests -v
python update_m3u.py
```

El validador no descarga la emisión completa: revisa el manifiesto y una muestra del primer segmento para detectar URLs muertas, páginas HTML de error y bloqueos HTTP evidentes.

## Variantes adicionales de Las Estrellas

Se añadieron tres endpoints HLS de la ficha pública de [Las Estrellas Latin America en Public IPTV](https://publiciptv.com/channels/lasestrellaslatinamericamx):

- `http://15.204.246.24:8080/LasEstrellasHD/index.m3u8`
- `http://190.93.224.42/CANAL-LAS-ESTRELLAS/index.m3u8`
- `http://209.14.115.253:8081/LAS-ESTRELLAS/index.m3u8`

Se etiquetan como variantes de respaldo, no como señal oficial ni como verificadas de antemano. El workflow comprueba su manifiesto y un segmento en cada ejecución y las deja detrás de cualquier variante que supere la prueba. Los resultados pueden cambiar por disponibilidad, geobloqueo o requisitos del proveedor.

Las páginas CXTv y Teleon muestran un reproductor web, pero no exponen el enlace HLS en el contenido que puede leer el actualizador; el iframe de Teleon además rechaza la lectura externa. La URL de México TV Live se carga como reproductor dinámico y su contenido no publica los tres manifiestos en el HTML disponible. No se inventan ni se derivan URLs a partir de IDs opacos.
