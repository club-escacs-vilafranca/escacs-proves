#!/usr/bin/env python3
"""Executa tools/jugadors.py (codi antic o nou) al banc de proves públic, amb les restriccions de privadesa:
només les dues jugadores autoritzades i sense nombre de socis. Tota la sortida va a un fitxer xifrat, mai als logs públics.
Ús (des de l'arrel de la còpia): python3 privat.py [--des AAAA-MM-DD] [--seguiment] [--fase X]"""
import importlib, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
args = sys.argv[1:]
sys.argv = ["jugadors.py"] + args          # abans d'importar: el mòdul llegeix --fase i --seguiment en importar-se
J = importlib.import_module("jugadors")
AUTORITZADES = ("382950", "400411")
_orig = J.llista_club
J.llista_club = lambda: [x for x in _orig() if str(x.get("id")) in AUTORITZADES]
J.socis_csv = lambda: None
J.main(args[args.index("--des") + 1] if "--des" in args else "2026-09-01")
