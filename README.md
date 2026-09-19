# WAGUE

Home is `/` — a centered swap card (pay token, receive token, amount, one CTA). This repo is **WAGUE**. It does not use another product's name, mascot, points, or leaderboard.

Quotes come from the live Hyperliquid **testnet** book via the official `hyperliquid-python-sdk` (`Info.l2_snapshot` / mids). The locked quote snapshot stores price, `fee_amount`, and qty. After accept, if the ledger already covers the pay asset, execute starts immediately. Otherwise the client shows a deposit address. The ledger credits only after confirmation (or local simulate-deposit). Then the API places a real Hyperliquid testnet spot **IOC** (`TIF=Ioc`, aggressive vs mid). Fill is settlement. Unfilled IOC is failure. There is no stub fill on this path.

Only **ETH/USDC** (UETH) is live. Spot is resolved from `spotMeta` as `@{universe_index}` / asset `10000+index`. BTC is listed in the picker as **unavailable on testnet** because testnet has no UBTC. Do not map BTC to a junk market.

## Run

```bash
cp .env.example .env
docker compose up --build
```

- Swap UI: [http://127.0.0.1:8472/](http://127.0.0.1:8472/)
- API: `http://127.0.0.1:8080` (published `127.0.0.1:8080:8080`)

## Hyperliquid testnet

`.env.example` sets `HL_NETWORK=testnet` and `HL_API_URL=https://api.hyperliquid-testnet.xyz`.

Quotes use the public `/info` book. No key is required for that.

To **execute**, export a testnet agent private key and restart compose:

```bash
export HL_AGENT_KEY_TESTNET=0x...
docker compose up --build
```

Never commit that key. The API refuses to start if `HL_MASTER_KEY`, `HL_WITHDRAW_KEY`, `HL_AGENT_KEY_MAINNET`, a mainnet host, `HL_NETWORK=mainnet`, or an agent key whose address equals `HL_MASTER_ADDRESS` is present.

If the key is missing, the UI still quotes. Execute returns `set HL_AGENT_KEY_TESTNET`.

## Seed users

| Email | Password | Role |
| --- | --- | --- |
| `client@desk.local` | `client-local` | client |
| `ops@desk.local` | `ops-local` | ops |
| `cto@desk.local` | `cto-local` | cto |

Use **Account** on `/` to sign in as the client.

## Demo deposit (no chain)

`GET /v1/deposits/address` returns one EVM address per client. ETH and USDC share it. BTC has no deposit rail.

If the pay asset is already on the ledger, accept skips the deposit step and reserves immediately.

Otherwise the card shows amount due, asset, and a copyable address. Status is rendered from the server (`accepted → reserved → filling → settled`).

For local demo, `POST /v1/deposits/simulate` (Idempotency-Key required) credits the ledger. Body is `{ "trade_id", "chain_tx_id" }` where `chain_tx_id` is a synthetic `sim-…` id. Execute waits until that credit succeeds.

Withdraw is out of scope. There is no withdraw UI.

## Honor / money

Postgres is the system of record. Amounts are decimal strings. Accept honors the locked quote (no last look) in one transaction: `SELECT quotes FOR UPDATE` and only if `quoted` and not expired and the kill switch is not engaged. Idempotency-Key is required on mutating POSTs.

`cloid = 0x + sha256(b"otc-hedge-v1|" + canonical trade uuid)[:16] hex`. It never appears in client JSON.

## Tests

```bash
docker compose exec api pytest -q
```

Expired quote is not honored, kill switch blocks new quotes, accept is idempotent.
