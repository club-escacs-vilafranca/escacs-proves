#!/usr/bin/env python3
"""FIDE -> tornejos dels jugadors del club (data/fide-tornejos.json) i comparació amb els que ja tenim (data/fide-pendents.json).
FIDE diu ON ha jugat cada jugador (nom, lloc, país, dates de les rondes ja jugades, ritme); les fonts del país en donen les partides.
Per a cada jugador amb codi FIDE, cada mes del tram i cada ritme (t=0 clàssic, 1 ràpid, 2 blitz) es demana la llista de tornejos puntuables
(a_indv_calculation.php, amb reintents perquè des de GitHub FIDE dona timeouts intermitents). No es desa cap dada dels rivals.
Ús: python3 tools/fide_tornejos.py [--mesos=AAAA-MM..AAAA-MM] (per defecte: gener de l'any en curs fins al mes passat)."""
import html as H, json, os, re, sys, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
URL = "https://ratings.fide.com/a_indv_calculation.php?id_number={id}&rating_period={per}-01&t={t}"
RITMES = {0: "Clàssic", 1: "Ràpid", 2: "Blitz"}
FONT_PER_PAIS = {"FRA": "FFE", "ITA": "Vesus", "ESP": "Info64"}
EXCLOSOS = re.compile(r"lliga\s+catalana|liga\s+catalana", re.I)     # la Lliga Catalana s'agafa del web de la FCE amb un altre procediment
SORTIDA, PENDENTS = "data/fide-tornejos.json", "data/fide-pendents.json"
OPC = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)


def sa(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", H.unescape(t or "")).encode("ascii", "ignore").decode().lower()).strip()


def mesos():
    avui = datetime.now(timezone.utc).date()
    if "mesos" in OPC:
        a, b = OPC["mesos"].split("..") if ".." in OPC["mesos"] else (OPC["mesos"], OPC["mesos"])
    else:
        a, b = f"{avui.year}-01", (avui.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    out, (y, m), (y2, m2) = [], map(int, a.split("-")), map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def una_vegada(fide, per, t, intents=4):
    for i in range(intents):
        try:
            rq = urllib.request.Request(URL.format(id=fide, per=per, t=t), headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
            return urllib.request.urlopen(rq, timeout=25).read().decode("utf-8", "replace")
        except Exception as e:
            print(f"    FIDE {per} t={t}: intent {i + 1} fallit ({type(e).__name__})", flush=True)
            time.sleep(4 * (i + 1))
    return None


def demana(fide, per, t):
    """HTML de la llista de tornejos d'un període; None si FIDE no respon després dels reintents.
    FIDE retorna de tant en tant (≈8 %) una resposta buida de 3 bytes a una consulta que sí té tornejos: un buit no es dona per bo fins que
    dues consultes més no el confirmen (es queda amb la resposta més llarga)."""
    h = una_vegada(fide, per, t)
    if h is None or len(h.strip()) >= 100:
        return h
    millor = h
    for _ in range(2):
        time.sleep(0.7)
        x = una_vegada(fide, per, t)
        if x is None:
            return None
        if len(x) > len(millor):
            millor = x
    return millor


def analitza(h):
    """[{event, nom, lloc, pais, inici, fi}] d'una resposta de FIDE (sense dades de rivals)."""
    out = []
    for m in re.finditer(r'report\.phtml\?event=(\d+)[^>]*>([^<]+)</a>.*?<strong>([^<]*)</strong>\s*((?:<span class="dates_span">[^<]*</span>\s*)+)', h, re.S):
        lloc = H.unescape(m.group(3)).strip()
        pais = lloc.split()[-1] if lloc.split() else ""
        dates = re.findall(r">(\d{4}-\d\d-\d\d)<", m.group(4))
        out.append({"event": m.group(1), "nom": H.unescape(m.group(2)).strip(), "lloc": " ".join(lloc.split()[:-1]), "pais": pais,
                    "inici": min(dates) if dates else None, "fi": max(dates) if dates else None})
    return out


def grup_base(nom):
    """Nom sense el grup/secció (Grup A, Group B, Torneo_C...) per ajuntar els grups d'un mateix torneig."""
    n = sa(nom)
    n = re.sub(r"\b(grup|group|grupo|torneo|open|cat|categoria)\s*[a-z0-9]\b$", "", n).strip()
    return n


def cap_resultat(r, club, fide_t):
    """True si un resultat que ja tenim (qualsevol font) correspon al torneig de FIDE per al mateix jugador."""
    if r.get("jugador") != club:
        return False
    ini, fi = r.get("inici") or r.get("fi"), r.get("fi")
    if not (ini and fi and fide_t["inici"]):
        return False
    marge = timedelta(days=4)
    try:
        a, b = date.fromisoformat(ini) - marge, date.fromisoformat(fi) + marge
        x, y = date.fromisoformat(fide_t["inici"]), date.fromisoformat(fide_t["fi"])
    except ValueError:
        return False
    if y < a or x > b:
        return False
    t1, t2 = set(sa(r.get("torneig")).split()), set(sa(fide_t["nom"]).split())
    return len(t1 & t2) >= max(1, min(len(t1), len(t2)) // 3)


def carrega(p, per_defecte):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else per_defecte


def main():
    club = carrega("data/jugadors.json", {"jugadors": []})["jugadors"]
    ms = mesos()
    print("Mesos:", ms[0], "→", ms[-1], "· jugadors amb codi FIDE:", sum(1 for j in club if j.get("fide")), flush=True)
    tornejos, fallades = {}, []
    for j in club:
        if not j.get("fide"):
            continue
        for per in ms:
            for t in RITMES:
                h = demana(j["fide"], per, t)
                if h is None:
                    fallades.append((j["nom"], per, t))
                    continue
                for x in analitza(h):
                    k = (j["nom"], x["event"])
                    e = tornejos.setdefault(k, {**x, "jugador": j["nom"], "ritmes": []})
                    e["inici"], e["fi"] = min(e["inici"], x["inici"]), max(e["fi"], x["fi"])
                    if RITMES[t] not in e["ritmes"]:
                        e["ritmes"].append(RITMES[t])
                time.sleep(1)
        print(f"  {j['nom']}: {sum(1 for k in tornejos if k[0] == j['nom'])} tornejos", flush=True)
    llista = sorted(tornejos.values(), key=lambda e: (e["inici"] or "", e["jugador"]))
    os.makedirs("data", exist_ok=True)
    json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mesos": ms, "fallades": [list(f) for f in fallades], "tornejos": llista},
              open(SORTIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # comparació amb el que ja tenim
    tenim = []
    for f in ("resultats-jugadors", "ffe-jugadors", "info64-jugadors"):
        tenim += carrega(f"data/{f}.json", {}).get("resultats", [])
    pendents, trobats, exclosos = [], 0, 0
    for e in llista:
        if EXCLOSOS.search(e["nom"]):
            exclosos += 1
            continue
        if any(cap_resultat(r, e["jugador"], e) for r in tenim):
            trobats += 1
            continue
        pendents.append({"jugador": e["jugador"], "nom": e["nom"], "lloc": e["lloc"], "pais": e["pais"], "inici": e["inici"], "fi": e["fi"], "ritmes": e["ritmes"],
                         "grup": grup_base(e["nom"]), "buscar_a": [FONT_PER_PAIS.get(e["pais"], "Chess-Results")] + (["Chess-Results"] if e["pais"] in FONT_PER_PAIS else [])})
    json.dump({"actualitzat": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pendents": pendents},
              open(PENDENTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Tornejos a FIDE: {len(llista)} · ja trobats: {trobats} · Lliga Catalana (a part): {exclosos} · pendents: {len(pendents)}")
    for p in pendents:
        print(f"  PENDENT {p['jugador']} · {p['inici']} · {p['nom'][:55]} · {p['lloc']} {p['pais']} → {' / '.join(p['buscar_a'])}")
    if fallades:
        print(f"::warning::FIDE no ha respost en {len(fallades)} consultes (després de 5 intents)")
        sys.exit(1)       # un resultat incomplet no es dona per bo: l'acció surt en vermell


if __name__ == "__main__":
    main()
