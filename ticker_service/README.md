# Ticker Service

FastAPI microservice that manages long-running KiteTicker connections, streams option data to Redis, and exposes REST endpoints for on-demand historical candles and subscription management. Instrument metadata and subscription state are persisted in TimescaleDB so the service can recover cleanly after restarts.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Multi-account configuration

1. Populate `tradingview-viz/Kite_FOdata_scripts/kite_accounts.yaml` (or point `KITE_ACCOUNTS_FILE` to a customised file).  
2. Each account entry can reference environment variables via the `${VAR_NAME}` syntax so secrets stay out of git.  
3. Access tokens are read from `Kite_FOdata_scripts/tokens/kite_token_<account>.json`. Keep one token file per account – the ticker service automatically picks them up on boot.  
4. If the YAML file is missing the service falls back to `KITE_API_KEY`, `KITE_API_SECRET` and `KITE_ACCESS_TOKEN` from the `.env` file for single-account mode.

## Runtime behaviour

- `SessionOrchestrator` loads every configured account and hands out async leases so historical fetches and live subscriptions never exceed Kite’s per-account limits.
- `instrument_registry` mirrors the exchange metadata (segments, expiries, strikes, etc.) in TimescaleDB and refreshes it once per trading day (IST). `/admin/instrument-refresh` forces a refresh on demand.
- `instrument_subscriptions` persists the active tokens. On startup the service reloads the table, revalidates each token against the registry, and redistributes the workload across every account that successfully authenticates. Any stale instruments are automatically deactivated in the table.
- `generator.MultiAccountTickerLoop` streams ticks for the active assignment set and immediately republishes them to Redis (`ticker:<prefix>:options`), including open interest when supplied by Kite. The loop idles if no subscriptions are present—there is no synthetic fallback.

## REST API

All endpoints are unauthenticated by default—protect them (reverse proxy, auth middleware) before exposing publicly.

- `GET /health` – service status plus per-account runtime metrics (`running`, `active_subscriptions`, account summary).
- `GET /subscriptions` – list subscription records (`?status=active|inactive` optional).
- `POST /subscriptions` – create/activate a subscription. Body:
  ```json
  {
    "instrument_token": 20535810,
    "requested_mode": "FULL",
    "account_id": "optional-account-alias"
  }
  ```
  The token is validated against the instrument registry and the loop is reloaded immediately.
- `DELETE /subscriptions/{instrument_token}` – deactivate a subscription and reload the loop.
- `GET /history` – fetch historical candles via KiteConnect. Query params:
  - `instrument_token` (required)
  - `from_ts`, `to_ts` (ISO datetimes)
  - `interval` (Kite interval string, default `minute`)
  - `account_id` (optional override)
  - `continuous`, `oi` (booleans; set `oi=true` to include open interest in the response)

Example:
```bash
curl "http://localhost:8080/history?instrument_token=20535810&from_ts=2025-10-28T09:30:00Z&to_ts=2025-10-28T10:00:00Z&interval=minute&oi=true"
```

## Observability

- Redis publishes are tagged with `settings.publish_channel_prefix` (`ticker:nifty:options`, `ticker:nifty:underlying` by default). Option payloads now include `oi`.
- `GET /health` reflects the number of active subscriptions, per-account instrument counts, and last tick timestamps.
- Logs indicate subscription reconciliation, account authentication issues, and instrument refresh events.

## Configuration tips

- `INSTRUMENT_DB_HOST/PORT/NAME/USER/PASSWORD` must point to the TimescaleDB instance shared with the broader platform.
- `INSTRUMENT_REFRESH_HOURS` controls how frequently the registry is considered stale (defaults to 12h) while IST new-day rollover is always honoured.
- `INSTRUMENT_CACHE_TTL_SECONDS` tunes the in-process metadata cache (default 300s).
- Make sure each `Kite_FOdata_scripts/tokens/kite_token_<account>.json` contains a valid `access_token`; missing or invalid tokens cause the corresponding account to be skipped during assignment.

## Token bootstrap workflow

- Populate `app/kite/.env` with shared keys and per-account credentials, and set `KITE_ACCOUNTS` (comma separated). Example:

```dotenv
KITE_ACCOUNTS=default,primary
KITE_API_KEY=xxxx
KITE_API_SECRET=yyyy
KITE_DEFAULT_USERNAME=...
KITE_DEFAULT_PASSWORD=...
KITE_DEFAULT_TOTP_KEY=BASE32...
KITE_PRIMARY_USERNAME=...
KITE_PRIMARY_PASSWORD=...
KITE_PRIMARY_TOTP_KEY=BASE32...
```

- To bootstrap tokens manually:

```bash
cd ticker_service
. .venv/bin/activate
python app/kite/token_bootstrap.py
```

- To run the full service (bootstrap + uvicorn) use the wrapper:

```bash
cd ticker_service
. .venv/bin/activate
python start_ticker.py  # PORT env var optional (default 8080)
```

During live market hours the ticker refuses to emit mock data—if any account lacks a valid token, startup fails so you can fix credentials instead of silently emitting fake values.
