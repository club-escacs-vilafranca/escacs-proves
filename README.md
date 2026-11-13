# escacs-proves

Banc de proves **públic** del Club d'Escacs Vilafranca. Té els mateixos workflows i el mateix codi que el repositori de la web (`PROVA · …`), però:

- Només s'executen a mà (Actions → Run workflow); no tenen horari.
- Només treballen amb dues jugadores autoritzades (`data/jugadors.json`).
- Els resultats **no es desen al repositori**: es xifren amb la clau pública `proves-public.asc` i es pugen com a artefacte; només el club els pot llegir i copiar al repositori privat.
- Si el script falla, l'acció surt en vermell (`pipefail`).
