#!/usr/bin/env python3
"""
telegram_bot.py — bot Telegram "dati su richiesta" per PS Prato Live.

L'utente scrive al bot (qualsiasi messaggio, oppure /ora) e riceve la
fotografia istantanea dell'occupazione del Pronto Soccorso di Prato, letta
dallo stesso dataset pubblico che alimenta la dashboard.

Non serve un server sempre acceso: gira come long-poll dentro un run di
GitHub Actions a lunga durata, che si auto-riavvia (vedi
.github/workflows/telegram-bot.yml). Dipendenza: solo `requests`.

Config via env:
  TG_BOT_TOKEN  token del bot creato con @BotFather (obbligatorio, tranne --test)
  DURATA_MIN    durata del loop in minuti (default 330 ~ 5,5h)

Uso:
  python telegram_bot.py           # avvia il long-poll (richiede TG_BOT_TOKEN)
  python telegram_bot.py --test    # stampa solo il messaggio, senza token
"""

import csv
import io
import os
import sys
import time

import requests

TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"

CSV_RAW = "https://raw.githubusercontent.com/iltempe/ps-prato/main/data/presenze.csv"
DASHBOARD = "https://iltempe.github.io/ps-prato/"

CODICI = ["rosso", "giallo", "verde", "azzurro", "bianco"]
EMOJI = {"rosso": "🔴", "giallo": "🟡", "verde": "🟢", "azzurro": "🔵", "bianco": "⚪"}

HTTP_TIMEOUT = 20


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def snapshot():
    """Ritorna (ts, {codice: {in_attesa, in_trattamento}}) dell'ultimo giro, o None."""
    r = requests.get(CSV_RAW, timeout=HTTP_TIMEOUT, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        return None
    last_ts = max(row["ts_scrape"] for row in rows)
    cur = {}
    for row in rows:
        if row["ts_scrape"] == last_ts:
            cur[row["codice"]] = {
                "att": _int(row.get("in_attesa")),
                "trt": _int(row.get("in_trattamento")),
            }
    return last_ts, cur


def fmt_ts(iso: str) -> str:
    """2026-09-12T14:30:01+02:00 -> '12/09 14:30'."""
    try:
        d, t = iso.split("T")
        y, m, day = d.split("-")
        hh, mm = t[:5].split(":")
        return f"{day}/{m} {hh}:{mm}"
    except Exception:
        return iso


def build_message() -> str:
    try:
        snap = snapshot()
    except Exception as e:
        return f"Dati non raggiungibili in questo momento ({e}). Riprova tra poco."
    if not snap:
        return "Dati non disponibili al momento, riprova tra poco."

    last_ts, cur = snap
    tot = cur.get("totali", {"att": 0, "trt": 0})
    att, trt = tot["att"], tot["trt"]
    presenti = att + trt

    per = " · ".join(
        f"{EMOJI[c]} {c} {cur.get(c, {}).get('att', 0) + cur.get(c, {}).get('trt', 0)}"
        for c in CODICI
    )

    return (
        f"🏥 PS Prato — adesso\n"
        f"Aggiornato: {fmt_ts(last_ts)}\n\n"
        f"👥 Presenti: {presenti}\n"
        f"⏳ In attesa: {att}\n"
        f"🩺 In trattamento: {trt}\n\n"
        f"Per codice colore:\n{per}\n\n"
        f"ℹ️ \"Presenti\" = quante persone ci sono adesso, non da quanto tempo "
        f"(i tempi di permanenza non sono in questo dato).\n"
        f"📊 Grafici e storico: {DASHBOARD}"
    )


WELCOME = (
    "Ciao! Sono il bot di PS Prato Live.\n"
    "Scrivimi qualsiasi messaggio (o /ora) e ti dico quante persone ci sono "
    "adesso al Pronto Soccorso di Prato.\n\n"
)


def send(chat_id, text):
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        print(f"sendMessage errore: {e}", file=sys.stderr)


def set_commands():
    """Registra i comandi mostrati nel menu del bot (best-effort)."""
    try:
        requests.post(
            f"{API}/setMyCommands",
            json={"commands": [
                {"command": "ora", "description": "Occupazione del PS adesso"},
                {"command": "help", "description": "Come funziona"},
            ]},
            timeout=HTTP_TIMEOUT,
        )
    except Exception:
        pass


def poll():
    if not TOKEN:
        print("TG_BOT_TOKEN non impostato: niente da fare.", file=sys.stderr)
        return 0

    set_commands()
    durata_min = _int(os.environ.get("DURATA_MIN", "330")) or 330
    fine = time.time() + durata_min * 60
    offset = None
    print(f"Bot avviato, loop per ~{durata_min} min")

    while time.time() < fine:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=45)
            data = r.json()
            if not data.get("ok"):
                # es. 409 se un altro poller e' ancora attivo (cambio catena): attendi
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = (msg.get("text") or "").strip().lower()
                if text in ("/start", "start"):
                    send(chat_id, WELCOME + build_message())
                elif text in ("/help", "help", "aiuto"):
                    send(chat_id, WELCOME + "Comandi: /ora — /help")
                else:
                    send(chat_id, build_message())
        except Exception as e:
            print(f"loop errore: {e}", file=sys.stderr)
            time.sleep(3)

    print("Fine finestra: esco (il workflow riavvia la catena).")
    return 0


def main():
    if "--test" in sys.argv:
        print(build_message())
        return 0
    return poll()


if __name__ == "__main__":
    raise SystemExit(main())
