#!/bin/zsh
# Avvia il gemello digitale: aggiorna i dati dal repo, crea l'ambiente se manca, apre il browser.
cd "$(dirname "$0")"
git -C .. pull --ff-only -q 2>/dev/null && echo "dati aggiornati (git pull)"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv && .venv/bin/pip install -q simpy scipy numpy pyyaml
fi
PORTA=$(grep -E '^\s+porta:' config.yaml | awk '{print $2}')
( sleep 3; open "http://localhost:${PORTA:-8765}" ) &
exec .venv/bin/python app.py
