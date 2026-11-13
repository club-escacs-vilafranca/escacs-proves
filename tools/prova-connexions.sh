#!/usr/bin/env bash
# Comprova si GitHub pot llegir les fonts que volem automatitzar. Només llegeix, no desa res a la web.
UA="Mozilla/5.0 (compatible; web-club-prova)"
prova() {
  nom="$1"; url="$2"
  codi=$(curl -sS -L -A "$UA" -o /tmp/p.out -w "%{http_code}" --max-time 40 "$url" 2>/tmp/p.err)
  mida=$(wc -c </tmp/p.out)
  echo "### $nom"
  echo "- URL: $url"
  echo "- Codi: **$codi** · Mida: $mida bytes $(head -c 150 /tmp/p.err)"
  echo "- Inici: \`$(head -c 200 /tmp/p.out | tr '\n\`' '  ')\`"
  echo
}
prova "Chess-Results (Obert 2026)" "https://s3.chess-results.com/tnr1340586.aspx?lan=9"
prova "Chess-Results (exportació Excel)" "https://s3.chess-results.com/tnr1340586.aspx?lan=9&art=1&flag=30"
prova "FCE: pàgina principal" "https://escacs.cat/"
prova "FCE: calendari" "https://escacs.cat/calendari/"
prova "FEDA: pàgina principal" "https://www.feda.org/"
prova "Instagram del club" "https://www.instagram.com/escacsvilafranca/"
prova "Instagram (perfil web)" "https://www.instagram.com/api/v1/users/web_profile_info/?username=escacsvilafranca"
