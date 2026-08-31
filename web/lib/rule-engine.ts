// Ports of algosathi/strategy/rule_strategy.py's condition evaluator, operating on an
// in-memory candle array instead of a pandas DataFrame. Same JSON definition schema works
// for both languages — see the plan doc / algosathi/strategy/rule_strategy.py docstring.
import { ema, macd, rsi, sma } from "./indicators";

export type Candle = { timestamp: string; open: number; high: number; low: number; close: number };

export type Operand =
  | { value: number }
  | { indicator: "close" | "open" | "high" | "low" }
  | { indicator: "sma" | "ema"; period: number; source?: "close" | "open" | "high" | "low" }
  | { indicator: "rsi"; period?: number; source?: "close" | "open" | "high" | "low" }
  | {
      indicator: "macd_line" | "macd_signal" | "macd_hist";
      fast_period?: number;
      slow_period?: number;
      signal_period?: number;
      source?: "close" | "open" | "high" | "low";
    };

export type Condition = {
  left: Operand;
  op: ">" | "<" | ">=" | "<=" | "crosses_above" | "crosses_below";
  right: Operand;
};

export type ConditionGroup = { operator: "and" | "or"; conditions: Condition[] };

export type StrategyDefinition = { entry: ConditionGroup; exit: ConditionGroup };

const PRICE_FIELDS = new Set(["open", "high", "low", "close"]);

function resolveOperand(operand: Operand, candles: Candle[]): number[] {
  if ("value" in operand) return new Array(candles.length).fill(operand.value);

  const indicator = operand.indicator;
  if (PRICE_FIELDS.has(indicator)) {
    return candles.map((c) => c[indicator as "open" | "high" | "low" | "close"]);
  }

  const source = "source" in operand && operand.source ? operand.source : "close";
  const sourceValues = candles.map((c) => c[source]);

  if (indicator === "sma") return sma(sourceValues, operand.period);
  if (indicator === "ema") return ema(sourceValues, operand.period);
  if (indicator === "rsi") return rsi(sourceValues, operand.period ?? 14);
  if (indicator === "macd_line" || indicator === "macd_signal" || indicator === "macd_hist") {
    const { line, signal, hist } = macd(
      sourceValues,
      operand.fast_period ?? 12,
      operand.slow_period ?? 26,
      operand.signal_period ?? 9
    );
    return { macd_line: line, macd_signal: signal, macd_hist: hist }[indicator];
  }
  throw new Error(`unknown indicator: ${indicator}`);
}

function evaluateCondition(condition: Condition, candles: Candle[]): boolean[] {
  const left = resolveOperand(condition.left, candles);
  const right = resolveOperand(condition.right, candles);
  const n = candles.length;
  const out = new Array(n).fill(false);

  for (let i = 0; i < n; i++) {
    const l = left[i];
    const r = right[i];
    if (Number.isNaN(l) || Number.isNaN(r)) continue;

    switch (condition.op) {
      case ">":
        out[i] = l > r;
        break;
      case "<":
        out[i] = l < r;
        break;
      case ">=":
        out[i] = l >= r;
        break;
      case "<=":
        out[i] = l <= r;
        break;
      case "crosses_above":
      case "crosses_below": {
        if (i === 0) break;
        const pl = left[i - 1];
        const pr = right[i - 1];
        if (Number.isNaN(pl) || Number.isNaN(pr)) break;
        out[i] =
          condition.op === "crosses_above" ? l > r && !(pl > pr) : l < r && !(pl < pr);
        break;
      }
    }
  }
  return out;
}

function evaluateGroup(group: ConditionGroup, candles: Candle[]): boolean[] {
  const seriesList = group.conditions.map((c) => evaluateCondition(c, candles));
  const n = candles.length;
  const out = new Array(n).fill(group.operator === "and");
  for (let i = 0; i < n; i++) {
    out[i] =
      group.operator === "and"
        ? seriesList.every((s) => s[i])
        : seriesList.some((s) => s[i]);
  }
  return out;
}

export type SignalType = "buy" | "exit" | null;

/** Evaluates the definition against the full candle history and returns the decision for
 * the *last* candle only — mirrors RuleStrategy.on_candles' single-current-bar contract. */
export function evaluateStrategy(definition: StrategyDefinition, candles: Candle[]): SignalType {
  if (candles.length < 2) return null;
  const entry = evaluateGroup(definition.entry, candles);
  if (entry[entry.length - 1]) return "buy";
  const exit = evaluateGroup(definition.exit, candles);
  if (exit[exit.length - 1]) return "exit";
  return null;
}
