# Multi-Market Trader Bot

Paper-first trading console for crypto, OKX-listed markets, and preview instruments. It includes a Go backend, React dashboard, Telegram controls, SQLite storage, risk/lot/margin calculator, and provider adapters for paper and OKX.

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

The Docker setup runs the Go API and React dashboard. Rebuild the API container after Go backend edits.

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
npm --prefix frontend install
```

Backend:

```bash
go run ./cmd/trader-api
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

- `GET /api/v1/status`
- `GET /api/v1/account`
- `GET /api/v1/live-readiness`
- `GET /api/v1/worker`
- `GET /api/v1/symbols`
- `GET /api/v1/watchlist`
- `POST /api/v1/symbols/activate`
- `GET /api/v1/settings`
- `PATCH /api/v1/settings`
- `POST /api/v1/position-size`
- `GET /api/v1/candles?symbol=BTC/USDT:USDT`
- `GET /api/v1/trades`
- `GET /api/v1/signals`
- `GET /api/v1/risk-events`
- `POST /api/v1/emergency-stop`
- `POST /api/v1/resume`
- `POST /api/v1/position/close/preview`
- `POST /api/v1/position/close/confirm`

Temporary `/api/*` compatibility routes are still exposed while the dashboard migration settles.

If `API_AUTH_TOKEN` is set, protected API calls must include either `X-API-Key: <token>` or `Authorization: Bearer <token>`.

## Tests

```bash
go test ./...
npm --prefix frontend run build
```
