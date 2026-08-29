import type { Trade } from "./supabase";

export type SymbolSummary = {
  symbol: string;
  realizedPnl: number;
  openQty: number;
  avgPrice: number;
};

export type EquityPoint = {
  timestamp: string;
  cumulativeRealizedPnl: number;
};

/**
 * Per-symbol realized P&L and open position, using the same weighted-average-cost method as
 * PaperBroker / algosathi/analytics.py, so these numbers always reconcile with the bot.
 */
export function summarizeBySymbol(trades: Trade[]): SymbolSummary[] {
  const positionQty = new Map<string, number>();
  const avgPrice = new Map<string, number>();
  const realizedPnl = new Map<string, number>();

  for (const trade of trades) {
    const symbol = trade.symbol;
    const qty = positionQty.get(symbol) ?? 0;
    const avg = avgPrice.get(symbol) ?? 0;

    if (trade.side === "buy") {
      const newQty = qty + trade.quantity;
      avgPrice.set(symbol, (avg * qty + trade.price * trade.quantity) / newQty);
      positionQty.set(symbol, newQty);
    } else {
      realizedPnl.set(
        symbol,
        (realizedPnl.get(symbol) ?? 0) + (trade.price - avg) * trade.quantity
      );
      const newQty = qty - trade.quantity;
      positionQty.set(symbol, newQty);
      if (newQty === 0) avgPrice.set(symbol, 0);
    }
  }

  const symbols = new Set([...positionQty.keys(), ...realizedPnl.keys()]);
  return [...symbols].sort().map((symbol) => ({
    symbol,
    realizedPnl: realizedPnl.get(symbol) ?? 0,
    openQty: positionQty.get(symbol) ?? 0,
    avgPrice: avgPrice.get(symbol) ?? 0,
  }));
}

/** Cumulative realized P&L over time, one point per SELL trade. */
export function equityCurve(trades: Trade[]): EquityPoint[] {
  const positionQty = new Map<string, number>();
  const avgPrice = new Map<string, number>();

  const points: EquityPoint[] = [];
  let cumulative = 0;
  for (const trade of trades) {
    const symbol = trade.symbol;
    const qty = positionQty.get(symbol) ?? 0;
    const avg = avgPrice.get(symbol) ?? 0;

    if (trade.side === "buy") {
      const newQty = qty + trade.quantity;
      avgPrice.set(symbol, (avg * qty + trade.price * trade.quantity) / newQty);
      positionQty.set(symbol, newQty);
    } else {
      cumulative += (trade.price - avg) * trade.quantity;
      const newQty = qty - trade.quantity;
      positionQty.set(symbol, newQty);
      if (newQty === 0) avgPrice.set(symbol, 0);
      points.push({ timestamp: trade.timestamp, cumulativeRealizedPnl: cumulative });
    }
  }

  return points;
}
