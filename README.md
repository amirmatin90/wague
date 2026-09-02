# WAGUE

Public swap page inspired by the Wagyu layout (centered card, amount-first type, asset chips, token picker). This repo is **WAGUE**. It does not use the Wagyu name, mascot, points, or leaderboard.

Home is `/` — a swap card. Quotes come from the live Hyperliquid **testnet** book. After you accept a firm quote, you deposit the pay asset. The ledger credits only after confirmation. Then the API places a real Hyperliquid testnet spot **IOC** with the official `hyperliquid-python-sdk`. Fill is settlement. There is no stub fill on this path.

Only **ETH/USDC** (UETH) is live. BTC is listed in the picker as unavailable because testnet has no UBTC.

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

Never commit that key. The API refuses to start if `HL_MASTER_KEY`, `HL_WITHDRAW_KEY`, `HL_AGENT_KEY_MAINNET`, or a mainnet host is present.

If the key is missing, the UI still quotes. Execute returns `set HL_AGENT_KEY_TESTNET`.

## Seed users

| Email | Password | Role |
| --- | --- | --- |
| `client@desk.local` | `client-local` | client |
| `ops@desk.local` | `ops-local` | ops |
| `cto@desk.local` | `cto-local` | cto |

Use **Account** on `/` to sign in as the client.

## Demo deposit (no chain)

After Swap, the card shows a deposit address and amount (`waiting → confirmed → swapping → done`).

For local demo, `POST /v1/deposits/simulate` (Idempotency-Key required) credits the ledger with a synthetic `chain_tx_id`. The UI button is labeled **Simulate deposit (local)**. Real path is: watch chain → credit → then IOC.

Withdraw is out of scope.

## Honor / money

Postgres is the system of record. Amounts are decimal strings. Accept honors the locked quote (no last look) in one transaction: `SELECT quotes FOR UPDATE` and only if `quoted` and not expired and the kill switch is not engaged. Idempotency-Key is required on mutating POSTs.

`cloid = 0x + sha256(b"otc-hedge-v1|" + canonical trade uuid)[:16] hex`. It never appears in client JSON.

## Tests

```bash
docker compose exec api pytest -q
```

Expired quote is not honored, kill switch blocks new quotes, accept is idempotent.
