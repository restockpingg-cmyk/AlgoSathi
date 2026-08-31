// Ports of algosathi/strategy/indicators.py. Series here are plain number[] aligned by
// index to the candle array; NaN marks "not enough history yet", mirroring pandas.

export function sma(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function ema(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN);
  const alpha = 2 / (period + 1);
  let prev = NaN;
  for (let i = 0; i < values.length; i++) {
    prev = Number.isNaN(prev) ? values[i] : values[i] * alpha + prev * (1 - alpha);
    out[i] = prev;
  }
  return out;
}

export function rsi(values: number[], period = 14): number[] {
  const out = new Array(values.length).fill(NaN);
  const alpha = 1 / period;
  let avgGain = NaN;
  let avgLoss = NaN;
  for (let i = 1; i < values.length; i++) {
    const delta = values[i] - values[i - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);
    avgGain = Number.isNaN(avgGain) ? gain : gain * alpha + avgGain * (1 - alpha);
    avgLoss = Number.isNaN(avgLoss) ? loss : loss * alpha + avgLoss * (1 - alpha);
    const rs = avgGain / avgLoss;
    out[i] = 100 - 100 / (1 + rs);
  }
  return out;
}

export function macd(
  values: number[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9
): { line: number[]; signal: number[]; hist: number[] } {
  const fast = ema(values, fastPeriod);
  const slow = ema(values, slowPeriod);
  const line = fast.map((v, i) => v - slow[i]);
  const signal = ema(line, signalPeriod);
  const hist = line.map((v, i) => v - signal[i]);
  return { line, signal, hist };
}
