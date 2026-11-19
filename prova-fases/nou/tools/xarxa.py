"""Peticions HTTP comunes (mateixa sessió de galetes per a totes les fonts)."""
import time, urllib.request, urllib.parse, http.cookiejar

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def req(url, data=None, headers=None, intents=4, espera=3, temps=60):
    h = {"User-Agent": UA, "Accept-Language": "ca,es;q=0.8", "Accept": "*/*"}
    h.update(headers or {})
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    for i in range(intents):
        try:
            with op.open(urllib.request.Request(url, data=data, headers=h), timeout=temps) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == intents - 1:
                raise
            time.sleep(espera * (i + 1))      # 429 i similars: esperar i reintentar
