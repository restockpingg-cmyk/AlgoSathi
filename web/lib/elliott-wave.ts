// Port of algosathi/strategy/elliott_wave.py. Kept deliberately line-for-line comparable with
// the Python so the browser backtest and the live bot cannot drift apart — the same reason
// rule-engine.ts mirrors rule_strategy.py.
import type { Candle, SignalType } from "./rule-engine";

export type ElliottParams = {
  zigzagPct: number;
  minRetracement: number;
  maxRetracement: number;
  targetExtension: number;
};

export const ELLIOTT_DEFAULTS: ElliottParams = {
  zigzagPct: 0.5,
  minRetracement: 0.382,
  maxRetracement: 0.786,
  targetExtension: 1.618,
};

type Pivot = {
  index: number;
  price: number;
  kind: "high" | "low";
  confirmedAt: number;
};

/** Causal zig-zag: a swing is only recognised once price has retraced `thresholdPct` away
 * from the extreme, so pivots never repaint and no decision depends on future candles. */
export function findPivots(candles: Candle[], thresholdPct: number): Pivot[] {
  if (candles.length === 0) return [];

  const threshold = thresholdPct / 100;
  const pivots: Pivot[] = [];
  let direction = 0; // 0 = undecided, 1 = tracking a swing high, -1 = tracking a swing low
  let highIdx = 0;
  let highPrice = candles[0].high;
  let lowIdx = 0;
  let lowPrice = candles[0].low;

  for (let i = 1; i < candles.length; i++) {
    const { high, low } = candles[i];

    if (direction >= 0 && high > highPrice) {
      highIdx = i;
      highPrice = high;
    }
    if (direction <= 0 && low < lowPrice) {
      lowIdx = i;
      lowPrice = low;
    }

    if (direction >= 0 && low <= highPrice * (1 - threshold)) {
      pivots.push({ index: highIdx, price: highPrice, kind: "high", confirmedAt: i });
      direction = -1;
      lowIdx = i;
      lowPrice = low;
    } else if (direction <= 0 && high >= lowPrice * (1 + threshold)) {
      pivots.push({ index: lowIdx, price: lowPrice, kind: "low", confirmedAt: i });
      direction = 1;
      highIdx = i;
      highPrice = high;
    }
  }

  return pivots;
}

/** Last-candle decision, mirroring ElliottWaveStrategy.on_candles. */
export function evaluateElliottWave(params: ElliottParams, candles: Candle[]): SignalType {
  if (candles.length < 2) return null;

  const pivots = findPivots(candles, params.zigzagPct);
  if (pivots.length < 3) return null;

  const lastBar = candles.length - 1;
  const prevClose = candles[lastBar - 1].close;
  const currClose = candles[lastBar].close;

  // A swing high confirming means price has already reversed off its peak — wave 3 is over.
  const latest = pivots[pivots.length - 1];
  if (latest.kind === "high" && latest.confirmedAt === lastBar) return "exit";

  const [wave0, wave1Top, wave2Low] = pivots.slice(-3);
  if (wave0.kind !== "low" || wave1Top.kind !== "high" || wave2Low.kind !== "low") return null;

  const wave1Size = wave1Top.price - wave0.price;
  if (wave1Size <= 0) return null;

  const target = wave2Low.price + params.targetExtension * wave1Size;
  if (prevClose < target && target <= currClose) return "exit";

  if (prevClose >= wave2Low.price && wave2Low.price > currClose) return "exit";

  // Elliott's hard rule: wave 2 may not retrace all of wave 1.
  if (!(wave0.price < wave2Low.price && wave2Low.price < wave1Top.price)) return null;

  const retracement = (wave1Top.price - wave2Low.price) / wave1Size;
  if (retracement < params.minRetracement || retracement > params.maxRetracement) return null;

  if (prevClose <= wave1Top.price && wave1Top.price < currClose) return "buy";

  return null;
}
