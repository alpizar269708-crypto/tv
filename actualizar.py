import requests

url = "https://iptv-org.github.io/iptv/languages/spa.m3u"
try:
    response = requests.get(url)
    if response.status_code == 200:
        with open("lista.m3u", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Copiado con éxito")
except Exception as e:
    print(f"Error: {e}")
