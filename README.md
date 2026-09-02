# WAGUE OTC Desk

Local institutional RFQ desk. This is not a retail swap. Quotes are firm for a TTL; accept does not reprice (no last look). The Hyperliquid venue is a stub that always fills immediately.

The previous repository README was empty and is replaced by this project document.

## What you get

- Modular Python 3.12 FastAPI monolith: identity, rfq, pricing, risk, trade, hyperliquid (stub only), ledger, recon, audit, admin, realtime
- PostgreSQL 16 as the only system of record and the only honor path (no Redis, no Kafka)
- TypeScript React portal: client RFQ desk and a thin ops/cto admin
- Docker Compose: `api`, `web`, `postgres`

Money is `NUMERIC` in Postgres. API sizes and prices are decimal strings. Floats are not used on the ledger or in persisted prices.

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://127.0.0.1:8080` (published as `127.0.0.1:8080:8080`, process binds `0.0.0.0:8080`)
- Portal: `http://127.0.0.1:8472`
- `GET /healthz` and `GET /readyz`

Definition of done path: sign in as the client → New RFQ for BTC/USDC → accept the firm quote on the confirm step → ticket moves accepted → reserved → hedging → filling → reconciling → settling → settled.

## Seed users

| Email | Password | Role |
| --- | --- | --- |
| `client@desk.local` | `client-local` | client |
| `ops@desk.local` | `ops-local` | ops |
| `cto@desk.local` | `cto-local` | cto |

The client is prefunded in BTC, ETH, and USDC. Desk inventory is seeded so the stub book can settle.

## Local stub rules

`.env.example` sets `HL_NETWORK=stub` only. The API refuses to start if:

- `HL_NETWORK` is anything other than `stub`
- `HL_AGENT_KEY`, `HL_MASTER_KEY`, or `WALLET_HOT_SEED_MAINNET` is set

Do not commit secrets. There is no Kubernetes, CI/CD, extra microservice, or real Hyperliquid key in this repo.

## Quote honor

Accept runs in a single Postgres transaction:

1. `SELECT quotes … FOR UPDATE`
2. Honor only if `status = quoted` AND `expires_at > now` AND the kill-switch row exists with `engaged = false`
3. A missing kill-switch row is treated as halted
4. Engaging the kill switch returns `423` on new RFQs

Hedge `cloid` is `0x` + first 16 bytes of `sha256(b'otc-hedge-v1|' + canonical uuid trade_id)` hex. It is unique on `trades.cloid` and is never included in client or admin JSON.

## HTTP API

Mutating POSTs (RFQ, accept, kill switch) require `Idempotency-Key`.

- `POST /v1/auth/login`
- `POST /v1/rfqs` body `{side, base, quote, base_qty}` → firm quote or `422 {code, message}` or `423` kill switch
- `GET /v1/rfqs/:id`
- `POST /v1/quotes/:id/accept`
- `GET /v1/trades/:id`
- `GET /v1/balances`
- `GET /v1/stream` (SSE)
- `GET /v1/admin/trades`, `/positions`, `/recon`
- `POST /v1/admin/kill-switch`
- `GET /healthz`, `GET /readyz`

Quoted pairs: BTC/USDC and ETH/USDC. Stub mids: BTC `97500`, ETH `3520`.

## Tests

```bash
docker compose exec api pytest -q
```

Covered: expired quote is not honored, kill switch blocks new quotes, accept is idempotent.

## Layout

```
apps/api     FastAPI monolith, Alembic, in-process workers
apps/web     Vite + React portal
compose.yml  api, web, postgres
.env.example HL_NETWORK=stub only
```
