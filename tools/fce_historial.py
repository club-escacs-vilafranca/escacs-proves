#!/usr/bin/env python3
"""Baixa de la FCE (cercaelo.php) l'Elo mensual (estàndard i ràpid) d'una tanda de jugadors.
Dades obertes de la federació. Desa data/fce_hist/p<inici>.json = {idJugador: {AAAAMM: [std, ràpid]}}.
Reprèn: no torna a demanar els ids que ja hi són. Para si hi ha 8 errors seguits."""
import argparse, json, os, re, sys, time, html, urllib.request

URL = "https://escacs.cat/components/com_fce/gmvw20/conn/cercaelo.php?idJugador=%s&type=1"


def demana(idj):
    cap = {"User-Agent": "Mozilla/5.0 (compatible; club-escacs-vilafranca)", "X-Requested-With": "XMLHttpRequest",
           "Referer": "https://escacs.cat/index.php/component/fce?op=2"}
    ultim = None
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL % idj, headers=cap), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            ultim = e
            time.sleep(3 * (i + 1))
    raise ultim


def analitza(txt):
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    out = {}
    for lin in re.split(r"[\r\n]+", txt):
        m = re.match(r"\s*(20\d{2}(?:0[1-9]|1[0-2]))\s+(\d{3,4})?\s*(\d{3,4})?\s*$", lin.replace("\t", " "))
        if m:
            out[m.group(1)] = [int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else None]
    # Només el 2025 en endavant, més l'últim valor anterior (la base per arrossegar l'Elo)
    base = [k for k in sorted(out) if k < "202501"][-1:]
    return {k: out[k] for k in sorted(out) if k >= "202501" or k in base}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inici", type=int, default=0)
    ap.add_argument("--max", type=int, default=3000)
    ap.add_argument("--pausa", type=float, default=1.0)
    a = ap.parse_args()
    ids = json.load(open("data/fce_ids.json"))[a.inici:a.inici + a.max]
    os.makedirs("data/fce_hist", exist_ok=True)
    ruta = "data/fce_hist/p%d.json" % a.inici
    dades = json.load(open(ruta)) if os.path.exists(ruta) else {}
    pend = [i for i in ids if i not in dades]
    print("Tanda %d: %d ids, %d pendents" % (a.inici, len(ids), len(pend)), flush=True)
    errors = 0
    t0 = time.time()
    for n, idj in enumerate(pend, 1):
        try:
            dades[idj] = analitza(demana(idj))
            errors = 0
        except Exception as e:
            errors += 1
            print("ERROR", idj, e, flush=True)
            if errors >= 8:
                print("Massa errors seguits: paro."); break
        if n % 200 == 0:
            json.dump(dades, open(ruta, "w"), separators=(",", ":"))
            print(n, "fets,", int(time.time() - t0), "s", flush=True)
        time.sleep(a.pausa)
    json.dump(dades, open(ruta, "w"), separators=(",", ":"))
    buits = sum(1 for v in dades.values() if not v)
    print("Desats %d jugadors (%d sense historial)" % (len(dades), buits))


main()
