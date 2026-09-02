export type Role = "client" | "ops" | "cto";

export type Session = {
  access_token: string;
  role: Role;
  email: string;
};

export type Quote = {
  quote_id: string;
  rfq_id: string;
  side: "buy" | "sell";
  base: string;
  quote: string;
  base_qty: string;
  quote_qty: string;
  price: string;
  fee_amount: string;
  fee_bps: string;
  ttl_ms: number;
  expires_at: string;
  status: string;
};

export type Trade = {
  trade_id: string;
  quote_id: string;
  rfq_id: string;
  side: "buy" | "sell";
  base: string;
  quote: string;
  base_qty: string;
  quote_qty: string;
  price: string;
  fee_amount: string;
  status: string;
  stages: { name: string; at: string }[];
  created_at: string;
  updated_at: string;
};

export type Balance = { asset: string; available: string; reserved: string };
export type Position = { asset: string; qty: string };
export type Recon = {
  recon_id: string;
  trade_id: string;
  status: string;
  client_base_qty: string;
  hedge_base_qty: string;
  client_price: string;
  hedge_price: string;
  notes: string;
};

function assertNoVenueIds(payload: unknown): void {
  if (payload && typeof payload === "object") {
    for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
      if (key === "cloid" || key === "oid") {
        throw new Error("venue identifiers must not appear in client payloads");
      }
      assertNoVenueIds(value);
    }
  }
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function newKey(): string {
  return crypto.randomUUID();
}

export async function api<T>(
  path: string,
  opts: {
    method?: string;
    token?: string;
    body?: unknown;
    idempotent?: boolean;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.idempotent) headers["Idempotency-Key"] = newKey();
  const response = await fetch(path, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, data.code ?? "ERROR", data.message ?? response.statusText);
  }
  assertNoVenueIds(data);
  return data as T;
}

export const login = (email: string, password: string) =>
  api<Session>("/v1/auth/login", { method: "POST", body: { email, password } });

export const createRfq = (token: string, body: { side: string; base: string; quote: string; base_qty: string }) =>
  api<Quote>("/v1/rfqs", { method: "POST", token, body, idempotent: true });

export const acceptQuote = (token: string, quoteId: string) =>
  api<Trade>(`/v1/quotes/${quoteId}/accept`, { method: "POST", token, idempotent: true });

export const getTrade = (token: string, tradeId: string) => api<Trade>(`/v1/trades/${tradeId}`, { token });
export const listTrades = (token: string) => api<{ trades: Trade[] }>("/v1/trades", { token });
export const getBalances = (token: string) => api<{ balances: Balance[] }>("/v1/balances", { token });
export const adminTrades = (token: string) => api<{ trades: Trade[] }>("/v1/admin/trades", { token });
export const adminPositions = (token: string) =>
  api<{ positions: Position[]; kill_switch: { present: boolean; engaged: boolean } }>(
    "/v1/admin/positions",
    { token },
  );
export const adminRecon = (token: string) => api<{ recon: Recon[] }>("/v1/admin/recon", { token });
export const setKillSwitch = (token: string, engaged: boolean) =>
  api<{ engaged: boolean }>("/v1/admin/kill-switch", {
    method: "POST",
    token,
    body: { engaged },
    idempotent: true,
  });
