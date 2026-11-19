#!/usr/bin/env python3
"""Circuit Català d'Oberts Internacionals -> data/calendari-altres.json.
Ús: python3 tools/circuit.py [carpeta_mostres]   (sense carpeta, descarrega d'escacs.cat)"""
import html, json, re, sys, urllib.request
from pathlib import Path

BASE = "https://escacs.cat/index.php/"
PRES = BASE + "presentacio/30838-xx-catalan-grand-prix-of-international-open-chess-tournaments-calendar-4"
TORN = BASE + "?option=com_fce_circuit&view=torneig&idTorneig="
SORTIDA = Path(__file__).resolve().parent.parent / "data" / "calendari-altres.json"


def baixa(url):
    rq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ClubEscacsVilafranca"})
    return urllib.request.urlopen(rq, timeout=60).read().decode("utf8", "ignore")


def net(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ids(pres):
    return list(dict.fromkeys(re.findall(r"idTorneig=(\d+)", pres)))


def iso(d):
    m = re.search(r"(\d\d)-(\d\d)-(\d{4})", d)
    return f"{m[3]}-{m[2]}-{m[1]}" if m else None


def analitza(i, t):
    nom = net((re.findall(r'<h4 class="module-title">(.*?)</h4>', t, flags=re.S) or [""])[0])
    camps = {net(a): net(b) for a, b in re.findall(
        r'<label>(.*?)</label>\s*<p class="form-control-static">(.*?)</p>', t, flags=re.S)}
    dates = re.findall(r"\d\d-\d\d-\d{4}", re.search(r"<label>Dates</label>(.*?)</div>", t, flags=re.S).group(1)) if "<label>Dates" in t else []
    if not nom or not dates:
        return None  # sense nom o dates confirmades: no es posa al calendari
    web = (re.findall(r'<label>Web del torneig</label>.*?href="([^"]+)"', t, flags=re.S) or [""])[0]
    ini, fi = iso(dates[0]), iso(dates[-1])
    adr = camps.get("Adreça", "")
    adr = "" if adr in ("-", "") else adr
    cat = camps.get("Categoria Int.", "")
    fmt = "Circuit Català d'Oberts" + (f" · categoria {cat}" if cat not in ("", "-") else "")
    pr = camps.get("Premis", "")
    if pr not in ("", "-"):
        fmt += f" · premis {pr}"
    return {
        "id": "cc" + i, "name": nom, "type": "oficial", "scope": "CAT",
        "place": adr, "format": fmt,
        "sch": {"kind": "dia" if ini == fi else "dies", "start": ini, "end": fi, "weeks": None},
        "source": "fce", "status": "ok",
        "url": web or TORN + i,
    }


def main():
    dir_ = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    pres = (dir_ / "circuit_presentacio.html").read_text("utf8", "ignore") if dir_ else baixa(PRES)
    evs = []
    for i in ids(pres):
        try:
            t = (dir_ / f"circuit_torneig_{i}.html").read_text("utf8", "ignore") if dir_ else baixa(TORN + i)
        except Exception as e:
            print("sense", i, e); continue
        e = analitza(i, t)
        print(i, e and (e["name"], e["sch"]["start"], e["sch"]["end"]) or "sense dates/nom: omès")
        if e:
            evs.append(e)
    try:
        antics = [e for e in json.loads(SORTIDA.read_text("utf8"))["events"] if not str(e.get("id", "")).startswith("cc")]
    except Exception:
        antics = []
    evs = antics + evs
    evs.sort(key=lambda e: e["sch"]["start"] or "")
    if not evs:
        print("Cap torneig: no toco el fitxer"); return
    SORTIDA.write_text(json.dumps({"events": evs}, ensure_ascii=False, indent=1) + "\n", "utf8")
    print(len(evs), "torneigs del Circuit")


main()
