#!/usr/bin/env python3
"""Avisa (incidència de GitHub, que arriba per correu) dels tornejos o jornades propers que tenen enllaç d'inscripció però no tenen
«Data límit d'inscripció». Sense la data, el botó d'inscripció es mostra sempre, també quan ja no es pot ningú inscriure.
Només s'avisa una vegada per torneig o jornada (data/brut/inscripcio_avisats.json).
Ús: python3 tools/avis_inscripcio.py [--cap-incidencia]   (amb GH_TOKEN a l'entorn i la comanda `gh`)"""
import datetime, glob, json, os, subprocess, sys

SITE = os.environ.get("SITE_URL", "https://club-escacs-vilafranca.pages.dev")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
AVUI = datetime.date.today().isoformat()


def pendents():
    out = []
    for f in sorted(glob.glob("data/torneig-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        for e in d.get("editions", []):
            e = {**e, **e.get("abans", {}), **e.get("durant", {}), **e.get("despres", {}), **e.get("avancat", {})}      # blocs del panell
            nom = "%s %s" % (d.get("name", f), e.get("year", ""))
            if e.get("jornades"):
                for j in e["jornades"]:
                    if j.get("d", "") >= AVUI and j.get("inscripcio") and not j.get("inscripcio_fins") and not j.get("suspesa"):
                        out.append(("%s/%s/%s" % (os.path.basename(f), e.get("year"), j["d"]), "%s · jornada del %s" % (nom, j["d"])))
            elif e.get("status") == "proper" and e.get("url") and not e.get("inscripcio_fins"):
                out.append(("%s/%s" % (os.path.basename(f), e.get("year")), nom))
    return out


def main():
    p = "data/brut/inscripcio_avisats.json"
    avisats = set(json.load(open(p))) if os.path.exists(p) else set()
    nous = [(k, n) for k, n in pendents() if k not in avisats]
    if not nous:
        print("Cap torneig sense data límit d'inscripció per avisar.")
        return
    cos = ("Aquests tornejos o jornades tenen enllaç d'inscripció però no tenen **data límit d'inscripció**, així que el botó «Inscriu-te» es mostra sempre.\n\n"
           "**Què cal fer:** entra al [backoffice](%s/admin/), obre el torneig (o la jornada) i omple «Data límit d'inscripció». El botó desapareix l'endemà d'aquesta data.\n\n" % SITE)
    cos += "\n".join("- " + n for _, n in nous)
    titol = "Falta la data límit d'inscripció: %s" % (nous[0][1] if len(nous) == 1 else "%d tornejos" % len(nous))
    if "--cap-incidencia" in sys.argv or not os.environ.get("GH_TOKEN"):
        print(titol + "\n\n" + cos)
        return
    r = subprocess.run(["gh", "issue", "create", "--title", titol, "--body", cos] + (["--repo", REPO] if REPO else []), capture_output=True, text=True)
    print(r.stdout, r.stderr)
    if r.returncode != 0:
        sys.exit(0)
    os.makedirs("data/brut", exist_ok=True)
    json.dump(sorted(avisats | {k for k, _ in nous}), open(p, "w"), indent=1)


if __name__ == "__main__":
    main()
