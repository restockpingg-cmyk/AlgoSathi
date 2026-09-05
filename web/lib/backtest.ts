// Port of algosathi/backtest.py + algosathi/simulation.py: feeds candles through the rule
// engine one at a time, filling at the *next* candle's open (avoids look-ahead bias), then
// reuses analytics.ts's P&L math (same shape as trades from Supabase) for metrics.
import { equityCurve, summarizeBySymbol } from "./analytics";
import {
  evaluateStrategy,
  type Candle,
  type SignalType,
  type StrategyDefinition,
} from "./rule-engine";
import type { Trade } from "./supabase";

export type RiskConfig = {
  orderQuantity: number;
  maxDailyLoss: number;
  maxOpenPositions: number;
};

export type BacktestResult = {
  totalTrades: number;
  realizedPnl: number;
  winRate: number;
  maxDrawdown: number;
  equityCurve: { timestamp: string; cumulativeRealizedPnl: number }[];
  trades: Trade[];
};

/** Decides what to do given all candles up to and including the current one. */
export type Evaluator = (history: Candle[]) => SignalType;

export function runBacktest(
  definition: StrategyDefinition,
  symbol: string,
  candles: Candle[],
  risk: RiskConfig
): BacktestResult {
  return runBacktestWith((history) => evaluateStrategy(definition, history), symbol, candles, risk);
}

export function runBacktestWith(
  evaluate: Evaluator,
  symbol: string,
  candles: Candle[],
  risk: RiskConfig
): BacktestResult {
  let quantity = 0;
  let avgPrice = 0;
  let realizedPnl = 0;
  const trades: Trade[] = [];

  const record = (side: "buy" | "sell", qty: number, price: number, timestamp: string) => {
    trades.push({
      id: trades.length,
      order_id: `bt-${trades.length}`,
      symbol,
      side,
      quantity: qty,
      price,
      timestamp,
      mode: "backtest",
    });
  };

  for (let i = 0; i < candles.length - 1; i++) {
    const history = candles.slice(0, i + 1);
    const signal = evaluate(history);
    if (!signal) continue;

    const price = candles[i + 1].open;
    const timestamp = candles[i + 1].timestamp;

    if (signal === "buy") {
      if (quantity > 0) continue; // already long
      if (realizedPnl <= -Math.abs(risk.maxDailyLoss)) continue; // daily loss limit
      const openPositionCount = 0; // quantity is 0 here (already-long case returned above)
      if (openPositionCount >= risk.maxOpenPositions) continue;
      const qty = risk.orderQuantity;
      const newQty = quantity + qty;
      avgPrice = (avgPrice * quantity + price * qty) / newQty;
      quantity = newQty;
      record("buy", qty, price, timestamp);
    } else {
      if (quantity <= 0) continue; // flat, nothing to exit
      const qty = quantity;
      realizedPnl += (price - avgPrice) * qty;
      quantity = 0;
      avgPrice = 0;
      record("sell", qty, price, timestamp);
    }
  }

  const curve = equityCurve(trades);
  const summary = summarizeBySymbol(trades);

  let wins = 0;
  let sells = 0;
  {
    let qty = 0;
    let avg = 0;
    for (const t of trades) {
      if (t.side === "buy") {
        const newQty = qty + t.quantity;
        avg = (avg * qty + t.price * t.quantity) / newQty;
        qty = newQty;
      } else {
        sells++;
        if ((t.price - avg) * t.quantity > 0) wins++;
        qty -= t.quantity;
        if (qty === 0) avg = 0;
      }
    }
  }

  let maxDrawdown = 0;
  {
    let runningMax = -Infinity;
    for (const p of curve) {
      runningMax = Math.max(runningMax, p.cumulativeRealizedPnl);
      maxDrawdown = Math.max(maxDrawdown, runningMax - p.cumulativeRealizedPnl);
    }
  }

  return {
    totalTrades: trades.length,
    realizedPnl: summary.reduce((sum, s) => sum + s.realizedPnl, 0),
    winRate: sells ? wins / sells : 0,
    maxDrawdown,
    equityCurve: curve,
    trades,
  };
}
