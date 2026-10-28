# Crypto Price Alert Bot (Telegram, Python)

Set crypto price alerts directly from Telegram and get a message when they trigger.
Prices come from the public **CoinGecko** API — no exchange account, no API key, no wallet.

## Commands
| Command | What it does |
|---|---|
| `/price BTC` | Current price and 24h change |
| `/alert BTC above 70000` | One-time alert when BTC goes above $70,000 |
| `/alert ETH below 2500` | One-time alert when ETH goes below $2,500 |
| `/alert SOL move 5` | Alert when the 24h change is ±5% or more (repeats at most every 6 h) |
| `/list` | Your active alerts |
| `/remove 2` | Delete alert #2 |

## Features
- Any coin listed on CoinGecko (common symbols built in, others looked up automatically)
- One price request per check for all alerts (rate-limit friendly)
- Alerts saved to `alerts.json` (survive restarts), atomic writes
- Optional whitelist of Telegram user IDs
- Offline self-test: `python price_alert_bot.py --test`

## Quick start
1. `pip install -r requirements.txt`
2. Create a bot with **@BotFather** and copy the token
3. Copy `.env.example` to `.env` and paste the token
4. `python price_alert_bot.py`, then open a chat with your bot and send `/help`

## Easy extensions
Percentage alerts from a set price, volume spikes, multiple fiat currencies, exchange prices
(Binance/Coinbase), Docker/systemd deployment on a VPS.

Educational demo — not financial advice.
