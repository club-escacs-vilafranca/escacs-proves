# escacs-proves

Banc de proves **públic** del Club d'Escacs Vilafranca. Té els mateixos workflows i el mateix codi que el repositori de la web (`PROVA · …`), però:

- Només s'executen a mà (Actions → Run workflow); no tenen horari.
- Només treballen amb dues jugadores autoritzades (`data/jugadors.json`).
- Els resultats es desen **xifrats** (`resultats-xifrats/*.gpg`, clau pública `proves-public.asc`): ningú no pot llegir-los sense la clau privada del club, que els copia al repositori privat.
- Si el script falla, l'acció surt en vermell (`pipefail`).
