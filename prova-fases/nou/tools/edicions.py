"""Càrrega de tornejos amb les seves edicions: les de dins del fitxer del torneig
(`editions`) i les de fitxers propis a data/edicions/<torneig>-<any>.json."""
import glob, json, os


def _json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def tornejos(arrel="."):
    """Retorna [(fitxer, dict_torneig)] amb `editions` completes (any descendent)."""
    ed = {}
    for p in sorted(glob.glob(os.path.join(arrel, "data", "edicions", "*.json"))):
        if os.path.basename(p) == "index.json":
            continue
        e = _json(p)
        ed.setdefault(e.get("torneig"), []).append(e)
    out = []
    for f in sorted(glob.glob(os.path.join(arrel, "data", "torneig-*.json"))):
        d = _json(f)
        d["_edicions_fitxer"] = bool(ed.get(d.get("id")))      # True: les edicions són fitxes pròpies (CMS: «Edicions»)
        d["editions"] = sorted(list(d.get("editions", [])) + ed.get(d.get("id"), []),
                               key=lambda e: str(e.get("year")), reverse=True)
        out.append((f, d))
    return out


def insc(e):
    """(inici, fins) de les inscripcions d'una edició: primer els camps estructurats (`abans.dades`), després els antics (`abans`)."""
    ab = e.get("abans") or {}
    dd = ab.get("dades") or {}
    return (dd.get("inscripcio_inici") or ab.get("inscripcio_inici") or "", dd.get("inscripcio_fins") or ab.get("inscripcio_fins") or "")


def genera_index(arrel="."):
    ids = sorted((os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(arrel, "data", "edicions", "*.json"))
                  if os.path.basename(p) != "index.json"), reverse=True)
    p = os.path.join(arrel, "data", "edicions", "index.json")
    nou = json.dumps(ids, indent=1)
    if not os.path.exists(p) or open(p).read() != nou:
        open(p, "w").write(nou)
        return True
    return False


if __name__ == "__main__":
    print("canviat" if genera_index() else "igual")
