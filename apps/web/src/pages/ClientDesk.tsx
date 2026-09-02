import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  acceptQuote,
  createRfq,
  getBalances,
  getTrade,
  listTrades,
  type Balance,
  type Quote,
  type Trade,
} from "../api";
import { clearSession, loadSession } from "../session";

const STAGES = ["accepted", "reserved", "hedging", "filling", "reconciling", "settling", "settled"];

function useTtl(expiresAt: string | null) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, []);
  if (!expiresAt) return { remainingMs: 0, expired: true };
  const remainingMs = Math.max(0, new Date(expiresAt).getTime() - now);
  return { remainingMs, expired: remainingMs <= 0 };
}

export function ClientDesk() {
  const session = loadSession()!;
  const [balances, setBalances] = useState<Balance[]>([]);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [base, setBase] = useState<"BTC" | "ETH">("BTC");
  const [qty, setQty] = useState("0.50");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [trade, setTrade] = useState<Trade | null>(null);
  const [recent, setRecent] = useState<Trade[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const ttl = useTtl(quote?.expires_at ?? null);

  async function refresh() {
    const [bals, trades] = await Promise.all([getBalances(session.access_token), listTrades(session.access_token)]);
    setBalances(bals.balances);
    setRecent(trades.trades);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load desk"));
  }, []);

  useEffect(() => {
    const stream = new EventSource(`/v1/stream?token=${session.access_token}`);
    stream.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type: string; trade_id?: string };
      if (payload.type === "balances.changed") {
        getBalances(session.access_token).then((b) => setBalances(b.balances)).catch(() => undefined);
      }
      if (payload.type === "trade.updated" && payload.trade_id) {
        getTrade(session.access_token, payload.trade_id)
          .then((next) => {
            setTrade(next);
            listTrades(session.access_token).then((t) => setRecent(t.trades)).catch(() => undefined);
          })
          .catch(() => undefined);
      }
    };
    return () => stream.close();
  }, [session.access_token]);

  const doneStages = useMemo(() => new Set((trade?.stages ?? []).map((s) => s.name)), [trade]);

  async function onRfq(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setTrade(null);
    try {
      const next = await createRfq(session.access_token, {
        side,
        base,
        quote: "USDC",
        base_qty: qty,
      });
      setQuote(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "RFQ failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAccept() {
    if (!quote) return;
    setBusy(true);
    setError("");
    try {
      const next = await acceptQuote(session.access_token, quote.quote_id);
      setTrade(next);
      setQuote(null);
      setConfirm(false);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Accept failed");
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <strong>WAGUE</strong>
          <span>Client portal · RFQ desk</span>
        </div>
        <div className="meta">
          {session.email} · {session.role}
          <button
            className="btn secondary"
            style={{ marginLeft: 12 }}
            onClick={() => {
              clearSession();
              window.location.href = "/";
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <div className="layout">
        <aside className="panel stack">
          <h2>Balances</h2>
          {balances.map((row) => (
            <div className="balance" key={row.asset}>
              <div>
                <div>{row.asset}</div>
                <div className="meta">reserved {row.reserved}</div>
              </div>
              <div className="mono">{row.available}</div>
            </div>
          ))}
        </aside>
        <main className="stack">
          <section className="panel">
            <h2>New RFQ</h2>
            <form className="row" onSubmit={onRfq}>
              <label>
                Side
                <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")}>
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
              </label>
              <label>
                Pair
                <select value={base} onChange={(e) => setBase(e.target.value as "BTC" | "ETH")}>
                  <option value="BTC">BTC/USDC</option>
                  <option value="ETH">ETH/USDC</option>
                </select>
              </label>
              <label>
                Base quantity
                <input className="mono" value={qty} onChange={(e) => setQty(e.target.value)} />
              </label>
              <button className="btn" disabled={busy} type="submit">
                Request firm quote
              </button>
            </form>
          </section>

          {quote ? (
            <section className="panel">
              <h2>Firm quote</h2>
              <p className="meta">Locked price. The desk will not reprice on accept.</p>
              <div className="quote-card">
                <div className="kv">
                  <span>Side / pair</span>
                  <strong>
                    {quote.side.toUpperCase()} {quote.base}/{quote.quote}
                  </strong>
                </div>
                <div className="kv">
                  <span>Price</span>
                  <strong>{quote.price}</strong>
                </div>
                <div className="kv">
                  <span>Base qty</span>
                  <strong>{quote.base_qty}</strong>
                </div>
                <div className="kv">
                  <span>Quote qty</span>
                  <strong>{quote.quote_qty}</strong>
                </div>
                <div className="kv">
                  <span>Fee</span>
                  <strong>
                    {quote.fee_amount} ({quote.fee_bps} bps)
                  </strong>
                </div>
                <div className="kv">
                  <span>TTL remaining</span>
                  <strong className="ttl">{(ttl.remainingMs / 1000).toFixed(1)}s</strong>
                </div>
              </div>
              <div style={{ marginTop: 16 }}>
                <button className="btn" disabled={busy || ttl.expired} onClick={() => setConfirm(true)}>
                  {ttl.expired ? "Quote expired" : "Accept quote"}
                </button>
              </div>
            </section>
          ) : null}

          {trade ? (
            <section className="panel">
              <h2>Trade {trade.trade_id.slice(0, 8)}</h2>
              <p className="meta">
                {trade.side.toUpperCase()} {trade.base_qty} {trade.base} @ {trade.price} · status {trade.status}
              </p>
              <div className="stages">
                {STAGES.map((name) => (
                  <div
                    key={name}
                    className={`stage ${doneStages.has(name) ? "done" : ""} ${trade.status === name ? "current" : ""}`}
                  >
                    {name}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {error ? <div className="error">{error}</div> : null}

          <section className="panel">
            <h2>Recent tickets</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Trade</th>
                  <th>Pair</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((row) => (
                  <tr key={row.trade_id}>
                    <td>{row.trade_id.slice(0, 8)}</td>
                    <td>
                      {row.base}/{row.quote}
                    </td>
                    <td>{row.side}</td>
                    <td>{row.base_qty}</td>
                    <td>{row.price}</td>
                    <td>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </main>
      </div>

      {confirm && quote ? (
        <div className="modal-back">
          <div className="modal stack">
            <h2>Confirm accept</h2>
            <p>
              You are accepting a firm quote for {quote.base_qty} {quote.base}/{quote.quote} at {quote.price}. The desk
              will not reprice. This commitment is final.
            </p>
            <div className="row">
              <button className="btn secondary" onClick={() => setConfirm(false)}>
                Cancel
              </button>
              <button className="btn" disabled={busy || ttl.expired} onClick={onAccept}>
                Accept firm quote
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
