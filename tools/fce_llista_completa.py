#!/usr/bin/env python3
"""Una sola consulta a la FCE: llista completa de federats amb Elo, categoria (descripcio) i variació. Desa data/fce_llista.json.gz. Dades obertes."""
import gzip, json, os, sys, urllib.parse, urllib.request, time

URL = "https://escacs.cat/components/com_fce/gmvw20/conn/resultatCerca.php"
dades = urllib.parse.urlencode({"idJugador": "", "nomLLarg": "", "elo_XYZ1": "", "elo_XYZ2": "", "idClub": "", "titol": "", "edat": "", "sexe": "",
                                "limitNoRows": "50000", "nomFitxa": "c_jugadors_0.xml", "dadesCercar": "jugadors_0.xml"}).encode()
cap = {"User-Agent": "Mozilla/5.0 (compatible; club-escacs-vilafranca)", "X-Requested-With": "XMLHttpRequest",
       "Referer": "https://escacs.cat/index.php/component/fce?op=2", "Origin": "https://escacs.cat",
       "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
ultim = None
for i in range(4):
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, data=dades, headers=cap), timeout=180) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        fila = (j.get("source") or {}).get("localdata") or j.get("localdata") or []
        def n(x):
            try: return int(float(x))
            except Exception: return 0
        sortida = [{"id": str(f.get("idJugador") or ""), "n": (f.get("nomLlarg") or "").strip(), "e": n(f.get("elo")), "er": n(f.get("eloR")),
                    "v": f.get("variacio"), "vr": f.get("variacioR"), "t": f.get("titol") or "", "d": (f.get("descripcio") or "").strip(),
                    "cl": (f.get("nomClub") or "").strip(), "s": f.get("sexe") or ""} for f in fila if f.get("nomLlarg")]
        if len(sortida) < 3000: raise RuntimeError("llista massa curta: %d" % len(sortida))
        os.makedirs("data", exist_ok=True)
        with gzip.open("data/fce_llista.json.gz", "wt", encoding="utf-8") as g:
            json.dump(sortida, g, ensure_ascii=False, separators=(",", ":"))
        cats = {}
        for x in sortida: cats[x["d"]] = cats.get(x["d"], 0) + 1
        print(len(sortida), "federats; camps de la primera fila:", sorted(fila[0].keys()))
        print("Categories:", dict(sorted(cats.items(), key=lambda z: -z[1])))
        sys.exit(0)
    except Exception as e:
        ultim = e; print("intent", i + 1, "fallit:", e); time.sleep(5 * (i + 1))
raise ultim
