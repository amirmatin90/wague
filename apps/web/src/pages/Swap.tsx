import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  acceptQuote,
  createQuote,
  getBalances,
  getTrade,
  listTokens,
  simulateDeposit,
  type Quote,
  type TokenInfo,
  type Trade,
} from "../api";
import { clearSession, loadSession, saveSession } from "../session";
import { login } from "../api";

const STEPS = ["accepted", "awaiting_deposit", "reserved", "swapping", "settling", "settled"];

function usdLabel(value?: string, fallback = "$0") {
  if (!value) return fallback;
  const n = Number(value);
  if (Number.isNaN(n)) return `$${value}`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function Swap() {
  const [session, setSession] = useState(loadSession());
  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [payAsset, setPayAsset] = useState("USDC");
  const [receiveAsset, setReceiveAsset] = useState("ETH");
  const [amount, setAmount] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [trade, setTrade] = useState<Trade | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<"pay" | "receive" | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("client@desk.local");
  const [password, setPassword] = useState("client-local");
  const [balances, setBalances] = useState<string>("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    listTokens().then((data) => setTokens(data.tokens)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!session) return;
    getBalances(session.access_token)
      .then((data) =>
        setBalances(data.balances.map((row) => `${row.asset} ${row.available}`).join(" · ")),
      )
      .catch(() => undefined);
  }, [session, trade?.status]);

  useEffect(() => {
    if (!session || !trade) return;
    const stream = new EventSource(`/v1/stream?token=${session.access_token}`);
    stream.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type?: string; trade_id?: string };
      if (payload.trade_id) {
        getTrade(session.access_token, payload.trade_id).then(setTrade).catch(() => undefined);
      }
    };
    return () => stream.close();
  }, [session, trade?.trade_id]);

  const cta = useMemo(() => {
    if (busy && !quote) return "Fetching quote";
    if (trade?.status === "settled") return "Done";
    return "Swap";
  }, [busy, quote, trade, amount]);

  function flip() {
    setPayAsset(receiveAsset);
    setReceiveAsset(payAsset);
    setQuote(null);
    setTrade(null);
  }

  function choose(asset: string) {
    const info = tokens.find((row) => row.asset === asset);
    if (!info?.available) return;
    if (picker === "pay") {
      setPayAsset(asset);
      if (asset === receiveAsset) setReceiveAsset(asset === "USDC" ? "ETH" : "USDC");
    } else if (picker === "receive") {
      setReceiveAsset(asset);
      if (asset === payAsset) setPayAsset(asset === "USDC" ? "ETH" : "USDC");
    }
    setPicker(null);
    setQuote(null);
    setTrade(null);
  }

  async function fetchQuote(nextAmount = amount) {
    if (!session) {
      setLoginOpen(true);
      return;
    }
    if (!nextAmount) return;
    setBusy(true);
    setError("");
    try {
      const next = await createQuote(session.access_token, {
        pay_asset: payAsset,
        receive_asset: receiveAsset,
        pay_qty: nextAmount,
      });
      setQuote(next);
    } catch (err) {
      setQuote(null);
      setError(err instanceof ApiError ? err.message : "Quote failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSwap() {
    if (!session) {
      setLoginOpen(true);
      return;
    }
    if (!quote) {
      await fetchQuote();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = await acceptQuote(session.access_token, quote.quote_id);
      setTrade(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Swap failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSimulate() {
    if (!session || !trade) return;
    setBusy(true);
    setError("");
    try {
      const next = await simulateDeposit(session.access_token, trade.trade_id);
      setTrade(next.trade);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulate deposit failed");
    } finally {
      setBusy(false);
    }
  }

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await login(email, password);
      saveSession(next);
      setSession(next);
      setLoginOpen(false);
      if (next.role !== "client") {
        window.location.href = "/admin";
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  const receiveDisplay = quote && quote.pay_asset === payAsset ? quote.receive_qty : "0";
  const visibleTokens = tokens.filter(
    (row) =>
      !search ||
      row.asset.toLowerCase().includes(search.toLowerCase()) ||
      row.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="pasture">
      <header className="nav">
        <div className="brand">WAGUE</div>
        <div className="nav-links">
          <span className="active">Swap</span>
        </div>
        {session ? (
          <button
            className="account-btn"
            onClick={() => {
              clearSession();
              setSession(null);
            }}
          >
            {session.email.split("@")[0]}
          </button>
        ) : (
          <button className="account-btn" onClick={() => setLoginOpen(true)}>
            Account
          </button>
        )}
      </header>

      <main className="stage">
        <section className="card">
          <h1>Swap</h1>
          <div className="leg">
            <div className="leg-label">You pay</div>
            <div className="leg-row">
              <input
                className="amount"
                inputMode="decimal"
                placeholder="0"
                value={amount}
                onChange={(event) => {
                  setAmount(event.target.value);
                  setQuote(null);
                  setTrade(null);
                }}
                onBlur={() => fetchQuote()}
              />
              <button className="chip" onClick={() => setPicker("pay")}>
                <span className={`token-dot ${payAsset}`}>{payAsset[0]}</span>
                {payAsset}
                <span>▾</span>
              </button>
            </div>
            <div className="usd">{usdLabel(quote?.pay_usd)}</div>
          </div>
          <button className="flip" onClick={flip} aria-label="Flip assets">
            ↕
          </button>
          <div className="leg dim">
            <div className="leg-label">You receive</div>
            <div className="leg-row">
              <div className="amount">{receiveDisplay}</div>
              <button className="chip" onClick={() => setPicker("receive")}>
                <span className={`token-dot ${receiveAsset}`}>{receiveAsset[0]}</span>
                {receiveAsset}
                <span>▾</span>
              </button>
            </div>
            <div className="usd">{usdLabel(quote?.receive_usd)}</div>
          </div>
          {quote ? (
            <div className="rate-row">
              <span>Rate</span>
              <span>
                1 ETH = {quote.price} USDC · fee {quote.fee_amount}
              </span>
            </div>
          ) : null}
          <button className="cta" disabled={busy || !amount} onClick={onSwap}>
            {cta}
          </button>
          {error ? <div className="banner">{error}</div> : null}

          {trade?.deposit ? (
            <div className="deposit-box">
              <label>Deposit {trade.deposit.asset} to continue</label>
              <div className="addr">{trade.deposit.address}</div>
              <div className="status-row">
                <span>Amount</span>
                <b>
                  {trade.deposit.amount} {trade.deposit.asset}
                </b>
              </div>
              <div className="status-row">
                <span>Status</span>
                <b>{trade.status === "awaiting_deposit" ? trade.deposit.status : trade.status}</b>
              </div>
              <div className="steps">
                {STEPS.map((name) => (
                  <span key={name} className={trade.stages.some((s) => s.name === name) || trade.status === name ? "on" : ""}>
                    {name.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
              {trade.status === "awaiting_deposit" ? (
                <button className="cta" disabled={busy} onClick={onSimulate}>
                  Simulate deposit (local)
                </button>
              ) : null}
              {trade.error_message ? <div className="banner">{trade.error_message}</div> : null}
            </div>
          ) : null}
          {session && balances ? <div className="balances">{balances}</div> : null}
        </section>
      </main>

      {picker ? (
        <div className="modal-back" onClick={() => setPicker(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <button className="close" onClick={() => setPicker(null)}>
              ×
            </button>
            <h2>{picker === "pay" ? "You pay" : "You receive"}</h2>
            <input
              className="search"
              placeholder="Search by token name"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {visibleTokens.map((row) => (
              <button
                key={row.asset}
                className="token-row"
                disabled={!row.available}
                onClick={() => choose(row.asset)}
              >
                <span className={`token-dot ${row.asset}`}>{row.asset[0]}</span>
                <span>
                  {row.asset}
                  <small>{row.available ? row.name : row.reason}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {loginOpen ? (
        <div className="modal-back" onClick={() => setLoginOpen(false)}>
          <form className="modal login-form" onClick={(event) => event.stopPropagation()} onSubmit={onLogin}>
            <button type="button" className="close" onClick={() => setLoginOpen(false)}>
              ×
            </button>
            <h2>Account</h2>
            <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
            <button className="cta" type="submit" disabled={busy}>
              Continue
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
