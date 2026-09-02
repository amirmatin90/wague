import { mockApi } from "./mock";

export type Role = "client" | "ops" | "cto";

export type Session = {
  access_token: string;
  role: Role;
  email: string;
};

export type TokenInfo = {
  asset: string;
  name: string;
  available: boolean;
  reason?: string;
};

export type Quote = {
  quote_id: string;
  pay_asset: string;
  receive_asset: string;
  pay_qty: string;
  receive_qty: string;
  price: string;
  fee_amount: string;
  fee_bps: string;
  pay_usd?: string;
  receive_usd?: string;
  ttl_ms: number;
  expires_at: string;
  status: string;
};

export type Deposit = {
  deposit_id: string;
  trade_id: string;
  asset: string;
  amount: string;
  address: string;
  status: string;
  chain_tx_id: string | null;
};

export type Trade = {
  trade_id: string;
  quote_id: string;
  pay_asset: string;
  receive_asset: string;
  pay_qty: string;
  receive_qty: string;
  price: string;
  status: string;
  error_message?: string | null;
  stages: { name: string; at: string }[];
  deposit?: Deposit;
  fill?: { filled_qty: string; avg_price: string } | null;
  base?: string;
  quote?: string;
  side?: string;
  base_qty?: string;
};

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

function newKey(): string {
  return crypto.randomUUID();
}

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

export async function api<T>(
  path: string,
  opts: { method?: string; token?: string; body?: unknown; idempotent?: boolean } = {},
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
  USE_MOCK
    ? mockApi.login(email)
    : api<Session>("/v1/auth/login", { method: "POST", body: { email, password } });

export const listTokens = () =>
  USE_MOCK ? mockApi.listTokens() : api<{ tokens: TokenInfo[] }>("/v1/tokens");

export const createQuote = (
  token: string,
  body: { pay_asset: string; receive_asset: string; pay_qty: string },
) =>
  USE_MOCK
    ? mockApi.createQuote(token, body)
    : api<Quote>("/v1/quotes", { method: "POST", token, body, idempotent: true });

export const acceptQuote = (token: string, quoteId: string) =>
  USE_MOCK
    ? mockApi.acceptQuote(token, quoteId)
    : api<Trade>(`/v1/quotes/${quoteId}/accept`, { method: "POST", token, idempotent: true });

export const getTrade = (token: string, tradeId: string) =>
  api<Trade>(`/v1/trades/${tradeId}`, { token });

export const simulateDeposit = (token: string, tradeId: string, chainTxId: string) =>
  USE_MOCK
    ? mockApi.simulateDeposit(token, {
        trade_id: tradeId,
        quote_id: "",
        pay_asset: "",
        receive_asset: "",
        pay_qty: "",
        receive_qty: "",
        price: "",
        status: "awaiting_deposit",
        stages: [],
        deposit: {
          deposit_id: "",
          trade_id: tradeId,
          asset: "USDC",
          amount: "0",
          address: "",
          status: "waiting",
          chain_tx_id: null,
        },
      })
    : api<{ deposit: Deposit; trade: Trade }>("/v1/deposits/simulate", {
        method: "POST",
        token,
        body: { trade_id: tradeId, chain_tx_id: chainTxId },
        idempotent: true,
      });

export const getDepositAddress = (token: string) =>
  USE_MOCK
    ? mockApi.getDepositAddress()
    : api<{ address: string; assets: string[] }>("/v1/deposits/address", { token });

export const getBalances = (token: string) =>
  USE_MOCK
    ? mockApi.getBalances()
    : api<{ balances: { asset: string; available: string; reserved: string }[] }>("/v1/balances", { token });

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
