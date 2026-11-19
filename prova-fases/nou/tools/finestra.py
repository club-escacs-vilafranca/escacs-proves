#!/usr/bin/env python3
"""Quants dies enrere ha de mirar el descobriment: els dies des de l'última execució bona + 3 de marge, amb un mínim de 7 i un màxim de 45.
Si l'últim fitxer és antic (p. ex. han fallat diverses execucions) la finestra s'amplia sola; si és d'avui, són 7 dies.
Ús: python3 tools/finestra.py data/resultats-jugadors.json   ->  escriu un número (dies)"""
import datetime, json, re, sys


def dies(ruta, minim=7, marge=3, maxim=45, per_defecte=30, ara=None):
    try:
        act = json.load(open(ruta, encoding="utf-8"))["actualitzat"]
        m = re.match(r"(\d{4})-(\d\d)-(\d\d)(?:T(\d\d):(\d\d))?", act)
        t = datetime.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0), int(m[5] or 0), tzinfo=datetime.timezone.utc)
        ara = ara or datetime.datetime.now(datetime.timezone.utc)
        return min(maxim, max(minim, (ara - t).days + marge))
    except Exception:
        return per_defecte


if __name__ == "__main__":
    print(dies(sys.argv[1]))
