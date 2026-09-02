import { FormEvent, useState } from "react";
import { ApiError, login } from "../api";
import { loadSession, saveSession } from "../session";

export function Login() {
  const existing = loadSession();
  if (existing) {
    window.location.replace(existing.role === "client" ? "/desk" : "/admin");
  }
  const [email, setEmail] = useState("client@desk.local");
  const [password, setPassword] = useState("client-local");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await login(email, password);
      saveSession(session);
      window.location.href = session.role === "client" ? "/desk" : "/admin";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-card stack" onSubmit={onSubmit}>
        <div className="brand">
          <strong>WAGUE</strong>
          <span>Institutional OTC desk</span>
        </div>
        <h1>Request for quote</h1>
        <p>Firm quotes only. Local stub venue. No last look.</p>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Enter desk"}
        </button>
      </form>
    </div>
  );
}
