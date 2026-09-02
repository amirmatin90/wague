import { useEffect, useState } from "react";
import {
  ApiError,
  adminPositions,
  adminRecon,
  adminTrades,
  setKillSwitch,
  type Position,
  type Recon,
  type Trade,
} from "../api";
import { clearSession, loadSession } from "../session";

export function AdminDesk() {
  const session = loadSession()!;
  const [tab, setTab] = useState<"trades" | "positions" | "recon">("trades");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [recon, setRecon] = useState<Recon[]>([]);
  const [engaged, setEngaged] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    const [t, p, r] = await Promise.all([
      adminTrades(session.access_token),
      adminPositions(session.access_token),
      adminRecon(session.access_token),
    ]);
    setTrades(t.trades);
    setPositions(p.positions);
    setEngaged(p.kill_switch.engaged);
    setRecon(r.recon);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load admin"));
  }, []);

  useEffect(() => {
    const stream = new EventSource(`/v1/stream?token=${session.access_token}`);
    stream.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type: string; engaged?: boolean };
      if (payload.type === "kill_switch" && typeof payload.engaged === "boolean") {
        setEngaged(payload.engaged);
      }
      if (payload.type === "trade.updated" || payload.type === "balances.changed") {
        refresh().catch(() => undefined);
      }
    };
    return () => stream.close();
  }, [session.access_token]);

  async function toggleKill(next: boolean) {
    try {
      const result = await setKillSwitch(session.access_token, next);
      setEngaged(result.engaged);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kill switch update failed");
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <strong>WAGUE</strong>
          <span>Operations · desk control</span>
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
      <div style={{ padding: "1.25rem 1.5rem" }} className="stack">
        {engaged ? <div className="banner">Kill switch engaged · new RFQs are halted</div> : null}
        <section className="panel">
          <h2>Kill switch</h2>
          <p className="meta">Single-row Postgres control. Missing row is treated as halted.</p>
          <div className="row">
            <button className="btn danger" disabled={engaged} onClick={() => toggleKill(true)}>
              Engage
            </button>
            <button className="btn secondary" disabled={!engaged} onClick={() => toggleKill(false)}>
              Release
            </button>
          </div>
        </section>
        <section className="panel">
          <div className="tabs">
            {(["trades", "positions", "recon"] as const).map((name) => (
              <button key={name} className={`tab ${tab === name ? "active" : ""}`} onClick={() => setTab(name)}>
                {name}
              </button>
            ))}
          </div>
          {tab === "trades" ? (
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
                {trades.map((row) => (
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
          ) : null}
          {tab === "positions" ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Desk qty</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((row) => (
                  <tr key={row.asset}>
                    <td>{row.asset}</td>
                    <td>{row.qty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {tab === "recon" ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Trade</th>
                  <th>Status</th>
                  <th>Client qty</th>
                  <th>Hedge qty</th>
                  <th>Client px</th>
                  <th>Hedge px</th>
                </tr>
              </thead>
              <tbody>
                {recon.map((row) => (
                  <tr key={row.recon_id}>
                    <td>{row.trade_id.slice(0, 8)}</td>
                    <td>{row.status}</td>
                    <td>{row.client_base_qty}</td>
                    <td>{row.hedge_base_qty}</td>
                    <td>{row.client_price}</td>
                    <td>{row.hedge_price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {error ? <div className="error">{error}</div> : null}
        </section>
      </div>
    </div>
  );
}
