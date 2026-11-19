#!/usr/bin/env python3
"""Comptador de minuts d'Actions del mes en curs (data/minuts.json) i avís a l'Andrea quan se'n gasta massa.

Suma la durada de cada execució del mes (arrodonida al minut, com cobra GitHub) a partir de l'API de GitHub (només cal GH_TOKEN i la comanda `gh`).
És una estimació: la factura oficial és a Configuració > Facturació de l'organització. Si es passa del 70 % o del 90 % del límit, es crea UNA incidència
de GitHub per cada llindar i mes (arriba per correu). El límit es posa amb la variable MINUTS_LIMIT (3000 al pla de 3000 minuts; 2000 al bàsic).
Ús: python3 tools/minuts.py [--cap-incidencia]"""
import datetime, json, math, os, subprocess, sys

REPO = os.environ.get("GITHUB_REPOSITORY", "club-escacs-vilafranca/web-club")
LIMIT = int(os.environ.get("MINUTS_LIMIT", "3000") or 3000)
LLINDARS = (70, 90)
D = "data/minuts.json"


def api(pagina, des):
    r = subprocess.run(["gh", "api", "-X", "GET", f"repos/{REPO}/actions/runs", "-f", "per_page=100", "-f", f"page={pagina}", "-f", f"created=>={des}",
                        "--jq", ".workflow_runs[] | [.name, .run_started_at, .updated_at, .conclusion] | @tsv"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return [l.split("\t") for l in r.stdout.splitlines() if l.strip()]


def temps(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    ara = datetime.datetime.now(datetime.timezone.utc)
    mes = ara.strftime("%Y-%m")
    des = ara.strftime("%Y-%m-01")
    per, n_runs, p = {}, 0, 1
    while p <= 30:
        files = api(p, des)
        for f in files:
            if len(f) < 3 or not f[1] or not f[2]:
                continue
            nom = f[0]
            minuts = math.ceil(max(0.0, (temps(f[2]) - temps(f[1])).total_seconds()) / 60) or 1
            per[nom] = per.get(nom, 0) + minuts
            n_runs += 1
        if len(files) < 100:
            break
        p += 1
    total = sum(per.values())
    pct = round(100 * total / LIMIT)
    antic = json.load(open(D, encoding="utf-8")) if os.path.exists(D) else {}
    avisats = antic.get("avisats", []) if antic.get("mes") == mes else []
    dia = ara.day
    dies_mes = (datetime.date(ara.year + (ara.month == 12), ara.month % 12 + 1, 1) - datetime.date(ara.year, ara.month, 1)).days
    previsio = round(total / max(dia, 1) * dies_mes)
    print(f"Minuts d'Actions de {mes}: ~{total} de {LIMIT} ({pct} %) en {n_runs} execucions · previsió a final de mes: ~{previsio}")
    for nom, m in sorted(per.items(), key=lambda x: -x[1])[:10]:
        print(f"  {m:5d} min  {nom}")
    nous = [l for l in LLINDARS if pct >= l and l not in avisats]
    if nous and "--cap-incidencia" not in sys.argv and os.environ.get("GH_TOKEN"):
        l = max(nous)
        cos = (f"S'han gastat **~{total} minuts de {LIMIT}** ({pct} %) a Actions aquest mes ({mes}); previsió a final de mes: ~{previsio}.\n\n"
               "Les accions que més gasten:\n" + "\n".join(f"- {m} min · {nom}" for nom, m in sorted(per.items(), key=lambda x: -x[1])[:6]) +
               "\n\nÉs una estimació a partir de la durada de les execucions; la xifra oficial és a Configuració > Facturació de l'organització. "
               "Convé no llançar execucions manuals llargues (p. ex. des de gener) fins a final de mes.")
        r = subprocess.run(["gh", "issue", "create", "--repo", REPO, "--title", f"Minuts d'Actions: {pct} % del límit de {mes}", "--body", cos], capture_output=True, text=True)
        print(r.stdout, r.stderr)
        if r.returncode == 0:
            avisats = sorted(set(avisats) | set(nous))
    os.makedirs("data", exist_ok=True)
    json.dump({"mes": mes, "actualitzat": ara.strftime("%Y-%m-%dT%H:%MZ"), "limit": LIMIT, "gastats": total, "percentatge": pct, "previsio_final_de_mes": previsio,
               "per_accio": dict(sorted(per.items(), key=lambda x: -x[1])), "avisats": avisats}, open(D, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:       # el comptador mai no ha de fer fallar l'acció que l'executa
        print("Comptador de minuts no disponible:", e)
