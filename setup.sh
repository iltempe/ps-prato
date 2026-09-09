#!/usr/bin/env bash
# Crea il repo su GitHub e carica il progetto in un colpo solo.
# Prerequisito: GitHub CLI installata e autenticata come iltempe.
#   - installa:   https://cli.github.com
#   - autentica:  gh auth login        (una volta sola)
#
# Uso:   bash setup.sh [nome-repo]     (default: ps-prato)
set -e

NOME="${1:-ps-prato}"

git init -q
git add .
git commit -q -m "scraper + analisi presenze PS Prato"
git branch -M main

# crea il repo sull'account autenticato e fa push
gh repo create "$NOME" --private --source=. --push

echo
echo "Repo creato e caricato: https://github.com/iltempe/$NOME"
echo "Ultimo passo (una volta): sul repo -> Settings > Actions > General"
echo "  -> Workflow permissions -> 'Read and write permissions' -> Save"
echo "Poi Actions > scrape-ps > Run workflow per il primo giro."
