# Multi-Market Trader Bot

Paper-first trading console for crypto, OKX-listed markets, and preview instruments. It includes a FastAPI backend, React dashboard, Telegram controls, SQLite storage, risk/lot/margin calculator, and provider adapters for paper and OKX.

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
/account
/livecheck
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

## OKX Notes

OKX is the main real provider. Public OKX market data works without API keys. Trading and private account data require OKX API credentials.

Required OKX environment fields:

```env
PROVIDER=okx
BOT_MODE=testnet
OKX_DEMO=true
OKX_MARKET_TYPE=swap
OKX_MARGIN_MODE=cross
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=
```

Important: OKX can only place real trades for instruments that exist on your OKX account/API. Some forex/commodity-style entries may be preview-only unless OKX lists that exact market.

## Live OKX Futures

Live futures trading is blocked unless all of these are set:

```env
BOT_MODE=live
ENABLE_REAL_TRADING=true
PROVIDER=okx
SYMBOL=BTC/USDT:USDT
OKX_DEMO=false
OKX_MARKET_TYPE=swap
OKX_MARGIN_MODE=cross
OKX_API_KEY=your_live_key
OKX_API_SECRET=your_live_secret
OKX_PASSPHRASE=your_live_passphrase
LIVE_TRADING_ACK=I_UNDERSTAND_LIVE_FUTURES_RISK
API_AUTH_TOKEN=choose_a_long_random_token
DEFAULT_LEVERAGE=1
MAX_LEVERAGE=3
MAX_POSITION_NOTIONAL=100
```

Set the same token for the dashboard build/runtime:

```env
VITE_API_TOKEN=choose_a_long_random_token
```

Use `/livecheck` in Telegram or `GET /api/live-readiness` before expecting real orders. Exits use reduce-only orders so a close action should not open a short position.

## API

Main endpoints:

- `GET /api/status`
- `GET /api/account`
- `GET /api/live-readiness`
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

If `API_AUTH_TOKEN` is set, protected API calls must include either `X-API-Key: <token>` or `Authorization: Bearer <token>`.

## Tests

```bash
pytest
npm --prefix frontend run build
```
