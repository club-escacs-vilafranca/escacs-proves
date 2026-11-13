#!/usr/bin/env python3
"""Importa un torneig de Chess-Results (llista d'inscrits, classificació i resultats de cada ronda)
i ho desa a data/resultats/<torneig>-<any>.json, que és el que llegeix la web.

Ús:
  python3 tools/importar_chessresults.py <torneig> <any> <url-chess-results>
  python3 tools/importar_chessresults.py obert-vilafranca 2026 "https://s3.chess-results.com/tnr1340586.aspx?lan=9"
Per provar sense xarxa: afegir --local <carpeta amb obert2026_art0.html, _art1.html, _art5.html>

Noms: es publiquen com «Nom Primer-cognom» (p. ex. «Silvia Serradell»), tal com s'ha acordat.
"""
import json, os, re, sys, time, datetime, urllib.request
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; web-club-importador)"
PARTICULES = {"de", "del", "della", "la", "las", "les", "los", "el", "i", "da", "di", "van", "von", "d'", "l'", "sant", "santa"}


def baixa(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ca,es;q=0.8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def taula(html):
    s = BeautifulSoup(html, "html.parser")
    tb = s.find("table", class_=re.compile("CRs"))
    if not tb:
        return [], s
    files = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])] for r in tb.find_all("tr")]
    return files, s


def nom_public(cr):
    """«Domene Mulyukov, Alexander» -> «Alexander Domene»."""
    if "," not in cr:
        return cr.strip()
    cognoms, nom = [x.strip() for x in cr.split(",", 1)]
    parts = cognoms.split()
    primer = []
    for p in parts:
        primer.append(p)
        if p.lower().rstrip("'") not in PARTICULES and not p.lower().endswith("'"):
            break
    nom = " ".join(w.capitalize() if w.isupper() else w for w in nom.split())
    return (nom + " " + " ".join(primer)).strip()


def num(x, tipus=float):
    x = (x or "").replace(",", ".").replace("½", ".5").strip()
    try:
        return tipus(x)
    except ValueError:
        return None


def trobacol(ix, *noms):
    """Índex de la primera columna amb algun d'aquests noms (Chess-Results els canvia segons el torneig), o None."""
    for n in noms:
        if n in ix:
            return ix[n]
    return None


def importa(torneig, any_, url, local=None):
    def pagina(art):
        if local:
            return open(os.path.join(local, f"obert2026_art{art}.html"), encoding="utf-8").read()
        time.sleep(1)
        h = baixa(f"{url}&art={art}")
        os.makedirs("data/brut/mostres_cr", exist_ok=True)       # còpia per poder revisar què ha llegit
        open(f"data/brut/mostres_cr/{torneig}-{any_}_art{art}.html", "w", encoding="utf-8").write(h)
        return h

    ins, s0 = taula(pagina(0))      # llista d'inscrits
    cla, _ = taula(pagina(1))       # classificació final
    cre, _ = taula(pagina(5))       # graella de creus per número d'inici
    titol = (s0.find("h2") or s0.find("title")).get_text(" ", strip=True)
    cap = ins[0]
    ix = {c: i for i, c in enumerate(cap)}
    print("Columnes d'inscrits:", cap)
    c_nom, c_fide, c_elo = trobacol(ix, "Nom"), trobacol(ix, "FIDE", "FideID"), trobacol(ix, "EloN", "Elo")
    c_sex, c_tip, c_gr, c_club = trobacol(ix, "Sexe"), trobacol(ix, "Tipus"), trobacol(ix, "Gr"), trobacol(ix, "Club/Ciutat")
    if c_nom is None:
        raise SystemExit("No s'ha trobat la columna «Nom» a la llista d'inscrits: " + str(cap))
    g = lambda f, i: f[i] if i is not None and i < len(f) else ""
    jug = []
    for f in ins[1:]:
        if len(f) < len(cap) or not f[0].isdigit():
            continue
        jug.append({
            "n": int(f[0]), "titol": f[1] if len(f) > 1 and c_nom != 1 else "", "nom": nom_public(f[c_nom]), "nom_cr": f[c_nom],
            "fide": num(g(f, c_fide), int), "elo": num(g(f, c_elo), int),
            "sexe": "F" if g(f, c_sex).lower() in ("w", "f") else "M", "tipus": g(f, c_tip),
            "gr": g(f, c_gr), "club": g(f, c_club),
        })
    per_n = {j["n"]: j for j in jug}
    # classificació: ordre, punts i desempats
    print("Columnes de classificació:", cla[0] if cla else None)
    ch = {c: i for i, c in enumerate(cla[0])} if cla else {}
    c_ini, c_ord, c_pts = trobacol(ch, "Núm. Ini.", "Núm.", "SNo"), trobacol(ch, "Ordre", "Rk.", "Lloc", "Rk"), trobacol(ch, "Pts.", "Punts", "Pts")
    for f in cla[1:]:
        if c_ini is None or c_pts is None or len(f) < len(cla[0]):
            break
        if not f[c_ini].isdigit():
            continue
        j = per_n.get(int(f[c_ini]))
        if j:
            j["ordre"] = int(f[c_ord]) if c_ord is not None and f[c_ord].isdigit() else None
            j["pts"] = num(f[c_pts])
            j["desempats"] = [num(f[ch[k]]) for k in ("Des1", "Des2", "Des3", "TB1", "TB2", "TB3") if k in ch][:3]
    if cla and not any("ordre" in j for j in jug):         # sense columna d'ordre: s'agafa l'ordre de les files
        for k, j in enumerate(sorted([j for j in jug if j.get("pts") is not None], key=lambda x: -x["pts"]), 1):
            j["ordre"] = k
    # rondes des de la graella de creus: cel·la «53b1» = rival 53, amb negres, resultat 1
    print("Columnes de la graella:", cre[0] if cre else None)
    ch = {c: i for i, c in enumerate(cre[0])} if cre else {}
    rcols = [c for c in (cre[0] if cre else []) if re.match(r"^\d+\.Rd$", c)]
    rondes = [[] for _ in rcols]
    for f in cre[1:]:
        if not rcols or len(f) < len(cre[0]) or not f[0].isdigit():
            continue
        n = int(f[0])
        for r, col in enumerate(rcols):
            m = re.match(r"^(\d+)([wb])([01½+-])$", f[ch[col]].strip())
            if m and m.group(2) == "w":     # cada partida es compta una vegada, des de les blanques
                x = m.group(3)
                res = {"1": "1-0", "0": "0-1", "½": "½-½", "+": "1-0", "-": "0-1"}[x]
                g = {"b": n, "n": int(m.group(1)), "res": res}
                if x in "+-":
                    g["inc"] = True        # guanyada o perduda per incompareixença
                rondes[r].append(g)
    for r in rondes:    # taulers: per puntuació dels dos jugadors, com Chess-Results
        r.sort(key=lambda g: (-(per_n[g["b"]].get("pts") or 0) - (per_n[g["n"]].get("pts") or 0), g["b"]))
    out = {
        "torneig": torneig, "any": str(any_), "font": url, "nom_torneig": titol,
        "importat": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "jugadors": [{k: v for k, v in j.items() if k != "nom_cr"} for j in jug],
        "rondes": rondes,
    }
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    local = None
    if "--local" in a:
        i = a.index("--local"); local = a[i + 1]; del a[i:i + 2]
    torneig, any_, url = a[:3]
    d = importa(torneig, any_, url, local)
    os.makedirs("data/resultats", exist_ok=True)
    p = f"data/resultats/{torneig}-{any_}.json"
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = "data/resultats/index.json"
    llista = json.load(open(ip)) if os.path.exists(ip) else []
    if f"{torneig}-{any_}" not in llista:
        llista.append(f"{torneig}-{any_}")
    json.dump(llista, open(ip, "w"), indent=1)
    print(f"{p}: {len(d['jugadors'])} jugadors, {len(d['rondes'])} rondes, {sum(len(r) for r in d['rondes'])} partides")
