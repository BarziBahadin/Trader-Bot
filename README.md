# Multi-Market Trader Bot

Paper-first trading console for crypto, forex, metals, and commodities. It includes a FastAPI backend, React dashboard, Telegram controls, SQLite storage, risk/lot/margin calculator, and provider adapters for paper, Binance, and cTrader.

## Safety Defaults

Real trading is blocked by default.

- `paper`: fake execution and safe testing
- `testnet`: exchange sandbox/testnet
- `live`: blocked unless `ENABLE_REAL_TRADING=true`
- `backtest`: simulation only

The emergency stop file is `STOP_BOT.txt`. If it exists, trading pauses immediately.

## Run With Docker

First run or dependency changes:

```bash
docker compose up --build
```

Normal development run:

```bash
docker compose up
```

The Docker setup mounts local source files into the containers. Backend code reloads through Uvicorn and the React dashboard hot-reloads through Vite, so most code edits do not need a Docker rebuild.

Dashboard:

```text
http://127.0.0.1:5173
```

API:

```text
http://127.0.0.1:8000
```

## Run Locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
```

Backend:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
npm --prefix frontend run dev
```

## Dashboard

The dashboard supports:

- symbol dropdown and watchlist
- crypto, forex, metals, and commodities metadata
- status cards and provider connection state
- candle chart preview
- risk percent, stop-loss distance, take-profit distance, leverage
- lot size, margin, risk, and tick-value preview
- emergency stop/resume
- two-step close-position confirmation
- latest signals, trades, and risk events

## Telegram Commands

Telegram is a control and alert surface.

```text
/status
/symbols
/watchlist
/set XAUUSD
/calc XAUUSD 1 50
/stop
/resume
/sell
/confirm CODE
/help
```

`/sell` only previews closing an open position. It requires `/confirm CODE`.

## cTrader Notes

cTrader is the preferred real provider for forex, metals, and commodities. The app includes a cTrader provider boundary and default cTrader instruments. Until credentials and the API session implementation are completed, it reports a clear cTrader configuration state and falls back to paper preview data for charts/calculations.

Required cTrader environment fields:

```env
PROVIDER=ctrader
CTRADER_CLIENT_ID=
CTRADER_CLIENT_SECRET=
CTRADER_ACCESS_TOKEN=
CTRADER_ACCOUNT_ID=
CTRADER_ENVIRONMENT=demo
```

Create API credentials through cTrader Open API: https://help.ctrader.com/open-api/

## API

Main endpoints:

- `GET /api/status`
- `GET /api/worker`
- `GET /api/symbols`
- `GET /api/watchlist`
- `POST /api/symbols/{symbol}/activate`
- `GET /api/settings`
- `PATCH /api/settings`
- `POST /api/position-size`
- `GET /api/candles/{symbol}`
- `GET /api/trades`
- `GET /api/signals`
- `GET /api/risk-events`
- `POST /api/emergency-stop`
- `POST /api/resume`
- `POST /api/position/close/preview`
- `POST /api/position/close/confirm`

Legacy endpoints like `/status`, `/trades`, and `/signals` still work.

## Tests

```bash
pytest
npm --prefix frontend run build
```
# Trader-Bot
