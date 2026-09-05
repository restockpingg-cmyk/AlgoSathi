import { NextRequest, NextResponse } from "next/server";
import { runBacktestWith, type Evaluator } from "@/lib/backtest";
import { ELLIOTT_DEFAULTS, evaluateElliottWave } from "@/lib/elliott-wave";
import { evaluateStrategy, type Candle } from "@/lib/rule-engine";
import { getServiceClient } from "@/lib/supabase-server";

// Supabase caps a single REST select at 1000 rows. Without paging, a backtest silently runs
// on the oldest 1000 candles and reports metrics as though it saw the whole window.
const PAGE_SIZE = 1000;

async function fetchAllCandles(
  supabase: ReturnType<typeof getServiceClient>,
  symbol: string,
  timeframeMinutes: number
): Promise<Candle[]> {
  const candles: Candle[] = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const { data, error } = await supabase
      .from("candles")
      .select("timestamp, open, high, low, close")
      .eq("symbol", symbol)
      .eq("timeframe_minutes", timeframeMinutes)
      .order("timestamp", { ascending: true })
      .range(offset, offset + PAGE_SIZE - 1);

    if (error) throw new Error(error.message);
    candles.push(...((data ?? []) as Candle[]));
    if (!data || data.length < PAGE_SIZE) return candles;
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const {
    definition,
    strategyType = "rule",
    params = {},
    symbol,
    timeframeMinutes = 5,
    orderQuantity = 1,
    maxDailyLoss = 5_000,
    maxOpenPositions = 1,
  } = body ?? {};

  if (!symbol) {
    return NextResponse.json({ error: "symbol is required" }, { status: 400 });
  }

  let evaluate: Evaluator;
  if (strategyType === "elliott_wave") {
    const merged = { ...ELLIOTT_DEFAULTS, ...params };
    evaluate = (history) => evaluateElliottWave(merged, history);
  } else if (strategyType === "rule") {
    if (!definition) {
      return NextResponse.json({ error: "definition is required" }, { status: 400 });
    }
    evaluate = (history) => evaluateStrategy(definition, history);
  } else {
    return NextResponse.json(
      { error: `Backtesting ${strategyType} in the browser is not supported yet.` },
      { status: 400 }
    );
  }

  const supabase = getServiceClient();
  let candles: Candle[];
  try {
    candles = await fetchAllCandles(supabase, symbol, timeframeMinutes);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Could not load candles" },
      { status: 500 }
    );
  }

  if (candles.length < 2) {
    return NextResponse.json(
      {
        error: `No candle data for ${symbol} (${timeframeMinutes}m). Run scripts/sync_candles.py first.`,
      },
      { status: 422 }
    );
  }

  const result = runBacktestWith(evaluate, symbol, candles, {
    orderQuantity,
    maxDailyLoss,
    maxOpenPositions,
  });

  return NextResponse.json({ ...result, candlesUsed: candles.length });
}
