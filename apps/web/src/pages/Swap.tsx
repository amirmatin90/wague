import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  acceptQuote,
  createQuote,
  getBalances,
  getDepositAddress,
  getTrade,
  listTokens,
  login,
  simulateDeposit,
  type Quote,
  type TokenInfo,
  type Trade,
} from "../api";
import { clearSession, loadSession, saveSession } from "../session";

const STATUS_STEPS = ["accepted", "reserved", "filling", "settled"] as const;

function usdLabel(value?: string) {
  if (!value) return "";
  const n = Number(value);
  if (Number.isNaN(n)) return `$${value}`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function displayStatus(status: string) {
  if (status === "swapping" || status === "settling" || status === "hedging") return "filling";
  if (status === "awaiting_deposit") return "accepted";
  return status;
}

function inFlight(status?: string) {
  return Boolean(
    status &&
      ["accepted", "awaiting_deposit", "reserved", "swapping", "settling", "filling"].includes(status),
  );
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
  const [quoting, setQuoting] = useState(false);
  const [picker, setPicker] = useState<"pay" | "receive" | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [email, setEmail] = useState("client@desk.local");
  const [password, setPassword] = useState("client-local");
  const [balances, setBalances] = useState<{ asset: string; available: string }[]>([]);
  const [depositAddress, setDepositAddress] = useState("");
  const [search, setSearch] = useState("");
  const [copied, setCopied] = useState(false);
  const quoteSeq = useRef(0);
  const executeLock = useRef(false);

  useEffect(() => {
    listTokens()
      .then((data) => setTokens(data.tokens))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!session || !amount || inFlight(trade?.status)) return;
    const handle = window.setTimeout(() => fetchQuote(amount), 280);
    return () => window.clearTimeout(handle);
  }, [session, amount, payAsset, receiveAsset]);

  useEffect(() => {
    if (!session) return;
    getBalances(session.access_token)
      .then((data) => setBalances(data.balances.map((row) => ({ asset: row.asset, available: row.available }))))
      .catch(() => undefined);
    getDepositAddress(session.access_token)
      .then((data) => setDepositAddress(data.address))
      .catch(() => undefined);
  }, [session, trade?.status]);

  useEffect(() => {
    if (!session || !trade) return;
    if (trade.status === "settled" || trade.status === "failed") return;
    const stream = new EventSource(`/v1/stream?token=${session.access_token}`);
    stream.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type?: string; trade_id?: string };
      if (payload.trade_id === trade.trade_id) {
        getTrade(session.access_token, payload.trade_id).then(setTrade).catch(() => undefined);
      }
    };
    return () => stream.close();
  }, [session, trade?.trade_id, trade?.status]);

  const liveQuote =
    quote && quote.pay_asset === payAsset && quote.receive_asset === receiveAsset && quote.pay_qty && amount
      ? quote
      : null;

  const availablePay = balances.find((row) => row.asset === payAsset)?.available;
  const funded =
    availablePay !== undefined && amount !== "" && Number(availablePay) >= Number(amount) && Number(amount) > 0;

  const cta = useMemo(() => {
    if (!session) return "Sign in to swap";
    if (trade?.status === "failed" || trade?.status === "settled") return "Start a new swap";
    if (quoting) return "Fetching quote";
    if (liveQuote) return `Swap ${liveQuote.pay_qty} ${liveQuote.pay_asset}`;
    if (!amount) return "Enter an amount";
    return "Fetching quote";
  }, [quoting, liveQuote, trade, amount, session]);

  function resetQuote() {
    quoteSeq.current += 1;
    setQuote(null);
    setTrade(null);
    setError("");
    executeLock.current = false;
  }

  function flip() {
    setPayAsset(receiveAsset);
    setReceiveAsset(payAsset);
    resetQuote();
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
    resetQuote();
  }

  async function fetchQuote(nextAmount = amount) {
    if (!session) {
      setLoginOpen(true);
      return;
    }
    if (!nextAmount) return;
    const seq = ++quoteSeq.current;
    setQuoting(true);
    setQuote(null);
    setError("");
    try {
      const next = await createQuote(session.access_token, {
        pay_asset: payAsset,
        receive_asset: receiveAsset,
        pay_qty: nextAmount,
      });
      if (seq !== quoteSeq.current) return;
      setQuote(next);
    } catch (err) {
      if (seq !== quoteSeq.current) return;
      setQuote(null);
      setError(err instanceof ApiError ? err.message : "Quote failed");
    } finally {
      if (seq === quoteSeq.current) setQuoting(false);
    }
  }

  async function commitSwap() {
    if (!session) {
      setLoginOpen(true);
      return;
    }
    if (trade?.status === "failed") {
      resetQuote();
      return;
    }
    if (!liveQuote) {
      await fetchQuote();
      return;
    }
    if (inFlight(trade?.status) || trade?.status === "settled") return;
    if (executeLock.current) return;
    executeLock.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await acceptQuote(session.access_token, liveQuote.quote_id);
      setTrade(next);
    } catch (err) {
      executeLock.current = false;
      setError(err instanceof ApiError ? err.message : "Swap failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSimulate() {
    if (!session || !trade || trade.status !== "awaiting_deposit") return;
    if (executeLock.current && trade.status !== "awaiting_deposit") return;
    setBusy(true);
    setError("");
    try {
      const next = await simulateDeposit(session.access_token, trade.trade_id, `sim-${crypto.randomUUID()}`);
      setTrade(next.trade);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Simulate deposit failed");
    } finally {
      setBusy(false);
    }
  }

  async function copyAddress(address: string) {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Could not copy address");
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

  const receiveDisplay = quoting ? "" : liveQuote?.receive_qty ?? "";
  const visibleTokens = tokens.filter(
    (row) =>
      !search ||
      row.asset.toLowerCase().includes(search.toLowerCase()) ||
      row.name.toLowerCase().includes(search.toLowerCase()),
  );
  const needsDeposit = trade?.status === "awaiting_deposit";
  const address = trade?.deposit?.address || depositAddress;
  const shownStatus = trade ? displayStatus(trade.status) : "";

  return (
    <div className="desk">
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
              resetQuote();
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
                  if (inFlight(trade?.status)) return;
                  setAmount(event.target.value);
                  resetQuote();
                }}
                onBlur={() => {
                  if (!inFlight(trade?.status)) fetchQuote();
                }}
                disabled={inFlight(trade?.status)}
              />
              <button className="chip" onClick={() => setPicker("pay")}>
                <span className={`token-dot ${payAsset}`}>{payAsset[0]}</span>
                {payAsset}
                <span>▾</span>
              </button>
            </div>
            <div className="usd">{liveQuote ? usdLabel(liveQuote.pay_usd) : ""}</div>
          </div>
          <button className="flip" onClick={flip} aria-label="Flip assets" disabled={inFlight(trade?.status)}>
            ↕
          </button>
          <div className="leg dim">
            <div className="leg-label">You receive</div>
            <div className="leg-row">
              {quoting ? (
                <div className="amount skeleton" aria-hidden="true" />
              ) : (
                <div className={`amount ${receiveDisplay ? "" : "placeholder"}`}>{receiveDisplay || ""}</div>
              )}
              <button className="chip" onClick={() => setPicker("receive")}>
                <span className={`token-dot ${receiveAsset}`}>{receiveAsset[0]}</span>
                {receiveAsset}
                <span>▾</span>
              </button>
            </div>
            <div className="usd">{liveQuote && !quoting ? usdLabel(liveQuote.receive_usd) : ""}</div>
          </div>
          {liveQuote && !trade ? (
            <div className="rate-row">
              <span>Fee</span>
              <span>{liveQuote.fee_amount}</span>
            </div>
          ) : null}
          {!inFlight(trade?.status) ? (
            <button
              className="cta"
              disabled={busy || quoting || (!amount && trade?.status !== "failed" && trade?.status !== "settled")}
              onClick={commitSwap}
            >
              {cta}
            </button>
          ) : null}
          {error ? <div className="banner">{error}</div> : null}

          {trade ? (
            <div className="status-box">
              <div className="status-row">
                <span>Status</span>
                <b>{shownStatus}</b>
              </div>
              <div className="steps">
                {STATUS_STEPS.map((name) => (
                  <span key={name} className={shownStatus === name || trade.stages.some((s) => displayStatus(s.name) === name) ? "on" : ""}>
                    {name}
                  </span>
                ))}
              </div>
              {trade.error_message && !needsDeposit ? <div className="banner">{trade.error_message}</div> : null}
            </div>
          ) : null}

          {needsDeposit ? (
            <div className="deposit-box">
              <label>
                Deposit {trade.deposit?.amount} {trade.deposit?.asset}
              </label>
              <div className="addr">
                <span>{address}</span>
                <button type="button" className="copy" onClick={() => copyAddress(address)}>
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <div className="status-row">
                <span>Amount due</span>
                <b>
                  {trade.deposit?.amount} {trade.deposit?.asset}
                </b>
              </div>
              <div className="status-row">
                <span>Status</span>
                <b>{trade.deposit?.status || trade.status}</b>
              </div>
              <button className="cta secondary" disabled={busy || trade.deposit?.status === "credited"} onClick={onSimulate}>
                Simulate deposit
              </button>
              {trade.error_message ? <div className="banner">{trade.error_message}</div> : null}
            </div>
          ) : null}
          {session ? (
            <div className="balances">
              {funded ? "Ledger covers this pay amount." : null}
              {balances.length
                ? balances.map((row) => `${row.asset} ${row.available}`).join(" · ")
                : null}
            </div>
          ) : null}
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
                  <small>{row.available ? row.name : row.reason || "unavailable on testnet"}</small>
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
