#!/usr/bin/env python3
"""Prova de lectura de fonts públiques per a un jugador autoritzat. No desa res fora de mostres/ i del resum de l'execució.
Ús: python3 tools/prova_fonts.py <id_fide> "<Cognoms, Nom>" ["<variant sense ñ>"]   (cada variant es prova per separat)"""
import os, re, sys, time, unicodedata, urllib.parse, urllib.request, html as H

FIDE = sys.argv[1]
NOMS = sys.argv[2:] or [""]
UA = "Mozilla/5.0 (compatible; club-escacs-vilafranca-proves; +https://github.com/club-escacs-vilafranca/escacs-proves)"
os.makedirs("mostres", exist_ok=True)
RES = []


def sa(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def get(nom, url, dades=None):
    t0 = time.time()
    try:
        rq = urllib.request.Request(url, urllib.parse.urlencode(dades).encode() if dades else None, headers={"User-Agent": UA, "Accept-Language": "ca,es,en;q=0.8"})
        r = urllib.request.urlopen(rq, timeout=45)
        b = r.read()
        codi = r.status
    except Exception as e:
        b, codi = b"", f"ERROR {type(e).__name__}: {str(e)[:80]}"
    f = "mostres/" + re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_") + ".html"
    if b:
        open(f, "wb").write(b)
    t = b.decode("utf-8", "replace")
    serr = len(re.findall(r"serradell", sa(t).lower()))
    RES.append((nom, url, codi, len(b), serr, round(time.time() - t0, 1)))
    time.sleep(1.5)
    return t


def inputs(h):
    return sorted(set(re.findall(r'<input[^>]*name="([^"]+)"', h)))


# 1. FIDE: fitxa i càlculs per període (llista de torneigs oficials amb l'ID)
get("FIDE fitxa", f"https://ratings.fide.com/profile/{FIDE}")
get("FIDE calendari de partides", f"https://ratings.fide.com/profile/{FIDE}/calculations")
# 2. Chess-Results: cerca de jugador per nom (formulari ASP.NET)
h = get("Chess-Results cerca (formulari)", "https://chess-results.com/SpielerSuche.aspx?lan=1")
RES.append(("Chess-Results camps del formulari", "", "", 0, 0, 0)); CAMPS = inputs(h)
# 3. FFE
h = get("FFE cerca de jugador", "https://www.echecs.asso.fr/ListeJoueurs.aspx")
# 4. Info64
get("Info64 portada", "https://info64.org/")
# 5. Vesus (Itàlia)
get("Vesus portada", "https://www.vesus.org/")
get("Vesus cerca", "https://www.vesus.org/?s=" + urllib.parse.quote(sa(NOMS[0].split(",")[0])))
# 6. Variants del nom (ñ / n) a la cerca de FIDE per nom
for n in NOMS:
    get("FIDE cerca nom " + n, "https://ratings.fide.com/incl_search_l.php?search=" + urllib.parse.quote(n) + "&simple=1")

out = ["## Resultat de la prova de fonts", "", "| Font | Codi | Bytes | «Serradell» | s |", "|---|---|---|---|---|"]
for nom, url, codi, mida, serr, s in RES:
    out.append(f"| {nom} | {codi} | {mida} | {serr} | {s} |")
out += ["", "Camps del formulari de Chess-Results: `" + ", ".join(CAMPS) + "`"]
txt = "\n".join(out)
print(txt)
open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), "a").write(txt + "\n")
