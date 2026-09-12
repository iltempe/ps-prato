#!/usr/bin/env python3
"""
telegram_bot.py — bot Telegram di PS Prato Live.

Due modalita':
- ON DEMAND: l'utente scrive /ora (o qualsiasi messaggio) e riceve subito la
  fotografia istantanea dell'occupazione del Pronto Soccorso di Prato.
- ISCRIZIONE 24h: con /start l'utente si iscrive e riceve l'aggiornamento ogni
  15 minuti per 24 ore, poi l'invio si ferma da solo. Con /stop si disattiva.

I dati sono letti dallo stesso dataset pubblico che alimenta la dashboard.
Non serve un server: gira come long-poll dentro un run di GitHub Actions a
lunga durata che si auto-riavvia (.github/workflows/telegram-bot.yml).

Privacy: la lista degli iscritti (chat id) NON sta nel repo pubblico; vive in
state/subs.json, persistito tramite la cache di GitHub Actions (privata al repo).

Config via env:
  TG_BOT_TOKEN  token del bot (@BotFather) — obbligatorio (tranne --test)
  DURATA_MIN    durata del loop in minuti (default 330 ~ 5,5h)

Uso:
  python telegram_bot.py           # long-poll (richiede TG_BOT_TOKEN)
  python telegram_bot.py --test    # stampa solo il messaggio, senza token
"""

import csv
import io
import json
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

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "subs.json")

INTERVALLO = 15 * 60          # 15 minuti tra un invio e l'altro
DURATA_ISCRIZIONE = 24 * 3600  # 24 ore
HTTP_TIMEOUT = 20


# --- dati ------------------------------------------------------------------

def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def snapshot():
    """(ts, {codice: {att, trt}}) dell'ultimo giro, o None."""
    r = requests.get(CSV_RAW, timeout=HTTP_TIMEOUT, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        return None
    last_ts = max(row["ts_scrape"] for row in rows)
    cur = {}
    for row in rows:
        if row["ts_scrape"] == last_ts:
            cur[row["codice"]] = {"att": _int(row.get("in_attesa")), "trt": _int(row.get("in_trattamento"))}
    return last_ts, cur


def fmt_ts(iso: str) -> str:
    try:
        d, t = iso.split("T")
        _, m, day = d.split("-")
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
    per = " · ".join(
        f"{EMOJI[c]} {c} {cur.get(c, {}).get('att', 0) + cur.get(c, {}).get('trt', 0)}" for c in CODICI
    )
    return (
        f"🏥 PS Prato — adesso\n"
        f"Aggiornato: {fmt_ts(last_ts)}\n\n"
        f"👥 Presenti: {att + trt}\n"
        f"⏳ In attesa: {att}\n"
        f"🩺 In trattamento: {trt}\n\n"
        f"Per codice colore:\n{per}\n\n"
        f"ℹ️ \"Presenti\" = quante persone ci sono adesso, non da quanto tempo "
        f"(i tempi di permanenza non sono in questo dato).\n\n"
        f"📊 Grafici e storico: {DASHBOARD}\n"
        f"Fonte: USL Toscana Centro (via prontosoccorso.live)"
    )


# --- stato iscritti (persistito via cache Actions) -------------------------

def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


# --- Telegram --------------------------------------------------------------

def send(chat_id, text):
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        print(f"sendMessage errore ({chat_id}): {e}", file=sys.stderr)


def set_commands():
    try:
        requests.post(
            f"{API}/setMyCommands",
            json={"commands": [
                {"command": "start", "description": "Aggiornamenti ogni 15 min per 24h"},
                {"command": "ora", "description": "Occupazione del PS adesso (una volta)"},
                {"command": "stop", "description": "Disattiva gli aggiornamenti"},
                {"command": "help", "description": "Come funziona"},
            ]},
            timeout=HTTP_TIMEOUT,
        )
    except Exception:
        pass


HELP = (
    "Sono il bot di PS Prato Live.\n\n"
    "• /start — ti iscrivo e ricevi l'occupazione del PS ogni 15 minuti per 24 ore, poi mi fermo.\n"
    "• /ora — te la mando una volta sola, adesso.\n"
    "• /stop — disattivo gli aggiornamenti.\n"
)


def handle(update, state):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    key = str(chat_id)
    text = (msg.get("text") or "").strip().lower()
    now = time.time()

    if text in ("/start", "start"):
        state[key] = {"until": now + DURATA_ISCRIZIONE, "last_sent": now}
        save_state(state)
        send(chat_id, "✅ Iscritto! Ti manderò l'aggiornamento ogni 15 minuti per 24 ore. "
                      "Scrivi /stop per fermarli.\n\n" + build_message())
    elif text in ("/stop", "stop"):
        if state.pop(key, None) is not None:
            save_state(state)
            send(chat_id, "⏹ Aggiornamenti disattivati. Scrivi /start per riattivarli o /ora per un dato singolo.")
        else:
            send(chat_id, "Non eri iscritto. /start per gli aggiornamenti automatici, /ora per un dato singolo.")
    elif text in ("/help", "help", "aiuto"):
        send(chat_id, HELP)
    else:  # /ora o qualsiasi altro messaggio: dato singolo on-demand
        send(chat_id, build_message())


def tick(state):
    """Invia gli aggiornamenti dovuti e rimuove le iscrizioni scadute."""
    now = time.time()
    changed = False
    scaduti = [k for k, s in state.items() if now >= s.get("until", 0)]
    for k in scaduti:
        send(int(k), "⏹ Le 24 ore sono finite: non riceverai più aggiornamenti automatici.\n"
                     "Scrivi /start per riattivarli.")
        del state[k]
        changed = True

    dovuti = [k for k, s in state.items() if now - s.get("last_sent", 0) >= INTERVALLO]
    if dovuti:
        text = build_message()
        for k in dovuti:
            send(int(k), text)
            state[k]["last_sent"] = now
            changed = True
    if changed:
        save_state(state)


def poll():
    if not TOKEN:
        print("TG_BOT_TOKEN non impostato: niente da fare.", file=sys.stderr)
        return 0
    try:
        me = requests.get(f"{API}/getMe", timeout=HTTP_TIMEOUT).json()
        if me.get("ok"):
            print(f"getMe ok: @{me['result'].get('username')}")
        else:
            print(f"getMe FALLITO (token non valido?): {me}", file=sys.stderr)
    except Exception as e:
        print(f"getMe errore: {e}", file=sys.stderr)
    set_commands()
    durata_min = _int(os.environ.get("DURATA_MIN", "330")) or 330
    fine = time.time() + durata_min * 60
    state = load_state()
    save_state(state)  # garantisce che state/subs.json esista (per la cache)
    offset = None
    print(f"Bot avviato, loop per ~{durata_min} min, iscritti caricati: {len(state)}")

    while time.time() < fine:
        try:
            params = {"timeout": 15}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=30)
            data = r.json()
            if data.get("ok"):
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    handle(upd, state)
            else:
                time.sleep(3)  # es. 409 durante il cambio catena
            tick(state)
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
