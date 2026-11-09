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
