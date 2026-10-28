#!/usr/bin/env python3
"""
Crypto Price Alert Bot for Telegram (demo)
=========================================
Set price alerts from Telegram and get notified when they trigger.
Data: CoinGecko public API (no API key). Alerts are stored in alerts.json.

Commands (in a private chat with the bot):
  /price BTC                 current price + 24h change
  /alert BTC above 70000     notify once when the price goes above 70,000 USD
  /alert ETH below 2500      notify once when the price goes below 2,500 USD
  /alert SOL move 5          notify when the 24h change is +/-5% or more (repeats at most every 6 h)
  /list                      your active alerts
  /remove 2                  delete alert #2
  /help

Usage:
  python price_alert_bot.py             run the bot
  python price_alert_bot.py --test      run a short offline self-test (no Telegram, no internet)
"""
import json
import os
import sys
import time
import datetime as dt

import requests

# ------------------------------------------------------------------ config ----
def load_env(path=".env"):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


load_env()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = {u.strip() for u in os.environ.get("ALLOWED_USER_IDS", "").split(",") if u.strip()}
CHECK_SEC = float(os.environ.get("CHECK_EVERY_SEC", "60"))
MOVE_COOLDOWN_H = float(os.environ.get("MOVE_ALERT_COOLDOWN_H", "6"))
ALERTS_FILE = "alerts.json"
CG = "https://api.coingecko.com/api/v3"

# common symbols -> CoinGecko ids (others are looked up with /search)
KNOWN = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin", "XRP": "ripple",
         "ADA": "cardano", "DOGE": "dogecoin", "TON": "the-open-network", "AVAX": "avalanche-2",
         "LINK": "chainlink", "DOT": "polkadot", "TRX": "tron", "MATIC": "matic-network", "POL": "polygon-ecosystem-token",
         "LTC": "litecoin", "SHIB": "shiba-inu", "PEPE": "pepe", "SUI": "sui", "ARB": "arbitrum", "OP": "optimism"}

HTTP = requests.Session()
HTTP.headers["User-Agent"] = "crypto-price-alert-bot/1.0"


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# -------------------------------------------------------------- price data ----
_id_cache = dict(KNOWN)


def coin_id(symbol):
    """Symbol -> CoinGecko id (cached). Returns None if unknown."""
    s = symbol.upper()
    if s in _id_cache:
        return _id_cache[s]
    try:
        r = HTTP.get(f"{CG}/search", params={"query": s}, timeout=10).json()
        coins = [c for c in r.get("coins", []) if str(c.get("symbol", "")).upper() == s]
        if coins:
            best = min(coins, key=lambda c: c.get("market_cap_rank") or 10 ** 9)   # highest market cap
            _id_cache[s] = best["id"]
            return best["id"]
    except Exception as e:
        log(f"search failed for {s}: {type(e).__name__}")
    return None


def prices(ids):
    """{id: (usd_price, change_24h_pct)} for many ids in one request."""
    if not ids:
        return {}
    try:
        r = HTTP.get(f"{CG}/simple/price", timeout=10,
                     params={"ids": ",".join(sorted(set(ids))), "vs_currencies": "usd", "include_24hr_change": "true"})
        r.raise_for_status()
        d = r.json()
        return {i: (v.get("usd"), v.get("usd_24h_change")) for i, v in d.items() if v.get("usd") is not None}
    except Exception as e:
        log(f"price request failed: {type(e).__name__}")
        return {}


def fmt_price(p):
    return f"${p:,.2f}" if p >= 1 else f"${p:.6g}"


# ------------------------------------------------------------------ alerts ----
def load_alerts():
    try:
        return json.load(open(ALERTS_FILE, encoding="utf-8"))
    except Exception:
        return {"next_id": 1, "items": []}


def save_alerts(a):
    tmp = ALERTS_FILE + ".tmp"
    json.dump(a, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, ALERTS_FILE)


def add_alert(store, chat, symbol, kind, value):
    cid = coin_id(symbol)
    if not cid:
        return f"❓ Unknown coin: {symbol}"
    if kind not in ("above", "below", "move"):
        return "Use: /alert BTC above 70000  |  /alert ETH below 2500  |  /alert SOL move 5"
    try:
        value = float(str(value).replace(",", ""))
        if value <= 0:
            raise ValueError
    except ValueError:
        return "The value must be a positive number."
    item = {"id": store["next_id"], "chat": chat, "symbol": symbol.upper(), "coin": cid,
            "kind": kind, "value": value, "created": time.time(), "last_fired": 0}
    store["next_id"] += 1
    store["items"].append(item)
    save_alerts(store)
    what = f"{kind} {fmt_price(value)}" if kind != "move" else f"24h move ≥ ±{value:g}%"
    return f"✅ Alert #{item['id']} set: {item['symbol']} {what}"


def check_alerts(store, send):
    """Check every alert once; send messages for triggered ones. Returns number fired."""
    items = store["items"]
    if not items:
        return 0
    px = prices([a["coin"] for a in items])
    fired, keep = 0, []
    now = time.time()
    for a in items:
        p = px.get(a["coin"])
        if not p:
            keep.append(a); continue
        price, chg = p
        hit, once = False, True
        if a["kind"] == "above" and price >= a["value"]:
            hit = True
        elif a["kind"] == "below" and price <= a["value"]:
            hit = True
        elif a["kind"] == "move" and chg is not None and abs(chg) >= a["value"]:
            once = False
            hit = now - a.get("last_fired", 0) >= MOVE_COOLDOWN_H * 3600
        if hit:
            fired += 1
            arrow = "📈" if (chg or 0) >= 0 else "📉"
            send(a["chat"], f"🔔 {a['symbol']} alert #{a['id']}: {fmt_price(price)}  {arrow} {chg:+.2f}% (24h)\n"
                            f"condition: {a['kind']} {a['value']:g}" + ("" if once else f"  (next check in {MOVE_COOLDOWN_H:g} h)"))
            if not once:
                a["last_fired"] = now
                keep.append(a)
        else:
            keep.append(a)
    store["items"] = keep
    save_alerts(store)
    return fired


# ---------------------------------------------------------------- commands ----
HELP = ("🤖 Crypto Price Alert Bot\n"
        "/price BTC — current price\n"
        "/alert BTC above 70000\n/alert ETH below 2500\n/alert SOL move 5  (24h change ±5%)\n"
        "/list — your alerts\n/remove 2 — delete alert #2")


def handle(store, chat, text):
    parts = text.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower().split("@")[0]
    if cmd in ("/start", "/help"):
        return HELP
    if cmd == "/price" and len(parts) >= 2:
        cid = coin_id(parts[1])
        p = prices([cid]).get(cid) if cid else None
        if not p:
            return f"❓ No price for {parts[1].upper()}"
        return f"{parts[1].upper()}: {fmt_price(p[0])}  ({p[1]:+.2f}% 24h)"
    if cmd == "/alert" and len(parts) == 4:
        return add_alert(store, chat, parts[1], parts[2].lower(), parts[3])
    if cmd == "/list":
        mine = [a for a in store["items"] if a["chat"] == chat]
        if not mine:
            return "No active alerts. Example: /alert BTC above 70000"
        return "Your alerts:\n" + "\n".join(
            f"#{a['id']} {a['symbol']} {a['kind']} " + (fmt_price(a['value']) if a['kind'] != 'move' else f"±{a['value']:g}%")
            for a in mine)
    if cmd == "/remove" and len(parts) == 2 and parts[1].lstrip("#").isdigit():
        n = int(parts[1].lstrip("#"))
        before = len(store["items"])
        store["items"] = [a for a in store["items"] if not (a["id"] == n and a["chat"] == chat)]
        save_alerts(store)
        return f"🗑 Alert #{n} removed." if len(store["items"]) < before else f"Alert #{n} not found."
    return "Unknown command. " + HELP


# ---------------------------------------------------------------- telegram ----
def tg(method, **params):
    try:
        d = HTTP.post(f"https://api.telegram.org/bot{TOKEN}/{method}", data=params, timeout=40).json()
        return d.get("result") if d.get("ok") else None
    except Exception as e:
        log(f"telegram {method} failed: {type(e).__name__}")
        return None


def send(chat, text):
    log(f"-> {chat}: {text.splitlines()[0]}")
    tg("sendMessage", chat_id=chat, text=text)


def run_bot():
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN is missing — copy .env.example to .env and fill it in.")
    me = tg("getMe")
    if not me:
        sys.exit("Telegram token rejected — check TELEGRAM_BOT_TOKEN.")
    log(f"bot @{me['username']} running — alerts only, no trading, no wallet")
    store, offset, last_check = load_alerts(), None, 0.0
    while True:
        for u in tg("getUpdates", timeout=20, offset=offset) or []:
            offset = u["update_id"] + 1
            m = u.get("message") or {}
            chat, user = (m.get("chat") or {}).get("id"), str((m.get("from") or {}).get("id"))
            if ALLOWED_USERS and user not in ALLOWED_USERS:
                continue
            reply = handle(store, chat, m.get("text") or "")
            if reply:
                send(chat, reply)
        if time.time() - last_check >= CHECK_SEC:
            last_check = time.time()
            n = check_alerts(store, send)
            if n:
                log(f"{n} alert(s) fired")


# --------------------------------------------------------------- self-test ----
def self_test():
    global prices, coin_id, ALERTS_FILE
    ALERTS_FILE = "alerts_test.json"
    if os.path.exists(ALERTS_FILE):
        os.remove(ALERTS_FILE)
    fake = {"bitcoin": (69000.0, 1.2), "ethereum": (2600.0, -6.1)}
    prices = lambda ids: {i: fake[i] for i in ids if i in fake}
    coin_id = lambda s: {"BTC": "bitcoin", "ETH": "ethereum"}.get(s.upper())
    out = []
    store = load_alerts()
    print(handle(store, 1, "/alert BTC above 70000"))
    print(handle(store, 1, "/alert ETH below 2500"))
    print(handle(store, 1, "/alert ETH move 5"))
    print(handle(store, 1, "/alert DOGE above 1"))
    print(handle(store, 1, "/list"))
    print("check 1 fired:", check_alerts(store, lambda c, t: out.append(t)))      # ETH move 5 -> fires
    fake["bitcoin"] = (70500.0, 3.0)
    print("check 2 fired:", check_alerts(store, lambda c, t: out.append(t)))      # BTC above -> fires; move in cooldown
    print(handle(store, 1, "/remove 2"))
    print(handle(store, 1, "/list"))
    print("\n--- messages sent ---\n" + "\n\n".join(out))
    os.remove(ALERTS_FILE)


if __name__ == "__main__":
    try:
        self_test() if "--test" in sys.argv else run_bot()
    except KeyboardInterrupt:
        print("\nstopped")
