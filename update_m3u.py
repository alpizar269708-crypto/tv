# ... (todo el código anterior de update_m3u.py se mantiene igual hasta el final)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for extinf, url in lista_final:
            nombre = re.search(r',(.*)$', extinf).group(1) if re.search(r',(.*)$', extinf) else ""
            nombre_limpio = limpiar_nombre(nombre)
            
            # Forzamos un tvg-id basado en el nombre si no tiene uno bueno
            # Esto ayuda a TiviMate a buscar la EPG por su cuenta si falla el script
            tvg_id_match = re.search(r'tvg-id="([^"]+)"', extinf)
            tid = tvg_id_match.group(1) if tvg_id_match else nombre_limpio.replace(" ", "")
            
            tvg_logo = re.search(r'tvg-logo="([^"]+)"', extinf)
            logo = tvg_logo.group(1) if tvg_logo else ""
            
            f.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-logo="{logo}",{nombre_limpio}\n{url}\n')
