#!/usr/bin/env bash
# Prepara la carpeta que publica Cloudflare Pages (_public): tot el web MENYS el que és intern (dades en brut, eines, documents, accions).
# A Cloudflare Pages: Build command = bash tools/publica.sh ; Build output directory = _public
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf _public && mkdir _public
tar cf - --exclude=./_public --exclude=./.git --exclude=./node_modules --exclude=./data/brut --exclude=./tools --exclude=./docs --exclude=./.github . | tar xf - -C _public
echo "Publicat a _public: $(find _public -type f | wc -l) fitxers (sense data/brut, tools, docs ni .github)"
