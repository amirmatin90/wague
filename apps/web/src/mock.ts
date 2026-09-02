import type { Deposit, Quote, Session, TokenInfo, Trade } from "./api";

const tokens: TokenInfo[] = [
  { asset: "ETH", name: "Ethereum", available: true },
  { asset: "USDC", name: "USD Coin", available: true },
  { asset: "BTC", name: "Bitcoin", available: false, reason: "unavailable on testnet" },
];

function quoteShape(payAsset: string, receiveAsset: string, payQty: string): Quote {
  const pay = Number(payQty) || 0;
  const receive = payAsset === "USDC" ? (pay / 3500).toFixed(8) : (pay * 3490).toFixed(2);
  const fee = payAsset === "USDC" ? (pay * 0.0005).toFixed(2) : (pay * 3490 * 0.0005).toFixed(2);
  return {
    quote_id: crypto.randomUUID(),
    pay_asset: payAsset,
    receive_asset: receiveAsset,
    pay_qty: payQty,
    receive_qty: receive,
    price: "3500.00",
    fee_amount: fee,
    fee_bps: "5.00",
    pay_usd: payAsset === "USDC" ? payQty : (pay * 3500).toFixed(2),
    receive_usd: receiveAsset === "USDC" ? receive : (Number(receive) * 3500).toFixed(2),
    ttl_ms: 20000,
    expires_at: new Date(Date.now() + 20000).toISOString(),
    status: "quoted",
  };
}

export const mockApi = {
  login: async (email: string): Promise<Session> => ({
    access_token: "mock-token",
    role: email.startsWith("ops") || email.startsWith("cto") ? (email.startsWith("cto") ? "cto" : "ops") : "client",
    email,
  }),
  listTokens: async () => ({ tokens }),
  createQuote: async (
    _token: string,
    body: { pay_asset: string; receive_asset: string; pay_qty: string },
  ): Promise<Quote> => quoteShape(body.pay_asset, body.receive_asset, body.pay_qty),
  acceptQuote: async (_token: string, quoteId: string): Promise<Trade> => ({
    trade_id: crypto.randomUUID(),
    quote_id: quoteId,
    pay_asset: "USDC",
    receive_asset: "ETH",
    pay_qty: "25.00",
    receive_qty: "0.00714286",
    price: "3500.00",
    status: "awaiting_deposit",
    stages: [{ name: "accepted", at: new Date().toISOString() }],
    deposit: {
      deposit_id: crypto.randomUUID(),
      trade_id: crypto.randomUUID(),
      asset: "USDC",
      amount: "25.00",
      address: "0x0000000000000000000000000000000000000001",
      status: "waiting",
      chain_tx_id: null,
    },
  }),
  getTrade: async (_token: string, trade: Trade): Promise<Trade> => trade,
  simulateDeposit: async (_token: string, trade: Trade): Promise<{ deposit: Deposit; trade: Trade }> => {
    const deposit = {
      ...(trade.deposit as Deposit),
      status: "credited",
      chain_tx_id: `sim-${crypto.randomUUID()}`,
    };
    return { deposit, trade: { ...trade, status: "reserved", deposit } };
  },
  getBalances: async () => ({
    balances: [
      { asset: "ETH", available: "0.00000000", reserved: "0.00000000" },
      { asset: "USDC", available: "0.00", reserved: "0.00" },
    ],
  }),
  getDepositAddress: async () => ({
    address: "0x0000000000000000000000000000000000000001",
    assets: ["ETH", "USDC"],
  }),
};
