import { NextRequest, NextResponse } from "next/server";
import { runBacktest } from "@/lib/backtest";
import { getServiceClient } from "@/lib/supabase-server";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const {
    definition,
    symbol,
    timeframeMinutes = 5,
    orderQuantity = 1,
    maxDailyLoss = 5_000,
    maxOpenPositions = 1,
  } = body ?? {};

  if (!definition || !symbol) {
    return NextResponse.json({ error: "definition and symbol are required" }, { status: 400 });
  }

  const supabase = getServiceClient();
  const { data: candles, error } = await supabase
    .from("candles")
    .select("timestamp, open, high, low, close")
    .eq("symbol", symbol)
    .eq("timeframe_minutes", timeframeMinutes)
    .order("timestamp", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!candles || candles.length < 2) {
    return NextResponse.json(
      { error: `No candle data for ${symbol} (${timeframeMinutes}m). Run scripts/sync_candles.py first.` },
      { status: 422 }
    );
  }

  const result = runBacktest(definition, symbol, candles, {
    orderQuantity,
    maxDailyLoss,
    maxOpenPositions,
  });

  return NextResponse.json(result);
}
