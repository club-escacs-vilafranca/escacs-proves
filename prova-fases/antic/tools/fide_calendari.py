#!/usr/bin/env python3
"""Calendari internacional de la FIDE (Main Events) -> data/calendari-fide.json (categoria FIDE, àmbit internacional).
Necessita un navegador real (Playwright): des dels servidors de GitHub només respon així. Només es posen els esdeveniments amb dates concretes."""
import json, re, sys, unicodedata
from playwright.sync_api import sync_playwright

ANYS = [int(a) for a in sys.argv[1:]] or [2026, 2027, 2028]
MESOS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
DATA = re.compile(r"^(\d{1,2}) ([A-Z][a-z]{2})(?: (\d{4}))? - (\d{1,2}) ([A-Z][a-z]{2})(?: (\d{4}))? / (.*)$")


# Només els esdeveniments del tipus que publica la FEDA (Mundials i Europeus individuals, d'edats, femenins, veterans, per equips, Olimpíada, Copa d'Europa de Clubs):
# no els oberts ni els torneigs d'elit, ni els campionats d'altres continents.
INC = re.compile(r"European (Individual|Women|Senior|Youth|Junior|Team|Chess Club Cup|Rapid|Blitz|School)|FIDE World (Cadet|Youth|Junior|Senior|Cup U|Team U|U7|Rapid U|Blitz U|Rapid Championships|Blitz Championships|Women)|FIDE World Cup U|Chess Olympiad|World Youth U16 Olympiad", re.I)
EXC = re.compile(r"African|Asian|Oceania|Commonwealth|Turkic|IPCA|Deaf|Disabilit|Corporate|Small Nations|University|FISU|ASEAN|Eastern|Western|Russian|Fischer|Freestyle|Total Chess|Global Chess|Candidates|Match|Grand Swiss|Super League|Schools|Amateur|European Union|People with|Congress|Team Rapid|Team Blitz", re.I)


def interessa(nom):
    return bool(INC.search(nom)) and not EXC.search(nom)


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]


def analitza(text, any_):
    ev, nom = [], None
    for ln in (l.strip() for l in text.splitlines()):
        if not ln:
            continue
        m = DATA.match(ln)
        if m and nom and interessa(nom):
            d1, m1, y1, d2, m2, y2, lloc = m.groups()
            if m1 in MESOS and m2 in MESOS:
                a1, a2 = int(y1 or any_), int(y2 or y1 or any_)
                ini = f"{a1}-{MESOS[m1]:02d}-{int(d1):02d}"
                fi = f"{a2}-{MESOS[m2]:02d}-{int(d2):02d}"
                if fi < ini:
                    fi = f"{a1 + 1}-{MESOS[m2]:02d}-{int(d2):02d}"
                lloc = re.sub(r"\s*\(([A-Z]{3})\)\s*$", r", \1", lloc).strip(" ,/")
                ev.append({"id": f"fide-{slug(nom)}-{ini[:4]}", "name": nom.rstrip(" *"), "type": "oficial", "scope": "INT", "place": lloc,
                           "format": "Calendari FIDE", "sch": {"kind": "dia" if ini == fi else "dies", "start": ini, "end": fi, "weeks": None},
                           "source": "fide", "status": "ok", "url": f"https://calendar.fide.com/majorcalendar.php?show=showYear&page={any_}"})
            nom = None
        else:
            nom = ln
    return ev


def main():
    tot = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for a in ANYS:
            pg = b.new_page()
            try:
                pg.goto(f"https://calendar.fide.com/majorcalendar.php?show=showYear&page={a}", wait_until="domcontentloaded", timeout=120000)
                pg.wait_for_timeout(15000)
                txt = pg.inner_text("body")
                i = txt.find("Main Events Calendar")
                evs = analitza(txt[i:] if i >= 0 else txt, a)
                print(a, len(evs), "esdeveniments")
                for e in evs:
                    tot.setdefault(e["id"], e)
            except Exception as e:
                print(a, "ERROR", str(e)[:200])
            pg.close()
        b.close()
    if not tot:
        sys.exit("Cap esdeveniment: no es toca el fitxer.")
    out = sorted(tot.values(), key=lambda e: e["sch"]["start"])
    json.dump({"events": out}, open("data/calendari-fide.json", "w"), ensure_ascii=False, indent=1)
    print("Total", len(out))


if __name__ == "__main__":
    main()
