"""Baixa de Chess-Results la performance dels rivals sense Elo (data/perf_pendents.json: {tnr: [snr, ...]}).
Desa data/perf_rivals.json {tnr: {snr: performance}}. Només fitxes públiques (art=9), amb pausa entre peticions."""
import json, sys, time, urllib.request, http.cookiejar
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(url, intents=3):
    for i in range(intents):
        try:
            with op.open(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == intents - 1:
                raise
            time.sleep(3 * (i + 1))


def num(x):
    try:
        return int(float(str(x).replace(",", ".")))
    except Exception:
        return None


def perf(t):
    for tab in BeautifulSoup(t, "html.parser").select("table.CRs1"):
        d = {}
        for tr in tab.find_all("tr"):
            c = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"], recursive=False)]
            if len(c) == 2:
                d[c[0]] = c[1]
        if "Name" in d or "Nom" in d or "Nombre" in d:
            return num(d.get("Performance rating") or d.get("Rendiment") or "")
    return None


pausa = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
pend = json.load(open("data/perf_pendents.json"))
try:
    res = json.load(open("data/perf_rivals.json"))
except Exception:
    res = {}
n = ok = 0
for tnr, snrs in pend.items():
    for sn in snrs:
        if str(sn) in res.get(tnr, {}):
            continue
        n += 1
        try:
            time.sleep(pausa)
            p = perf(req(f"https://s1.chess-results.com/tnr{tnr}.aspx?lan=1&art=9&snr={sn}"))
        except Exception as e:
            print(f"tnr{tnr} snr{sn}: error {e}")
            continue
        res.setdefault(tnr, {})[str(sn)] = p
        ok += p is not None
        print(f"tnr{tnr} snr{sn}: {p}")
json.dump(res, open("data/perf_rivals.json", "w"), indent=1, sort_keys=True)
print(f"## Performance de rivals: {ok} trobades de {n} consultades")
