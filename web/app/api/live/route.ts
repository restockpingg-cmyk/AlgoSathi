import { NextResponse } from "next/server";
import { getServiceClient } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/** Everything the live page needs, in one round trip so the panel updates atomically rather
 * than showing a status from one moment next to trades from another. */
export async function GET() {
  const supabase = getServiceClient();

  const [statuses, controls, signals, trades] = await Promise.all([
    supabase.from("bot_status").select("*").order("symbol"),
    supabase.from("bot_controls").select("*").eq("id", 1).maybeSingle(),
    supabase.from("signals").select("*").order("created_at", { ascending: false }).limit(25),
    supabase.from("trades").select("*").order("timestamp", { ascending: false }).limit(25),
  ]);

  const failure = [statuses, controls, signals, trades].find((r) => r.error);
  if (failure?.error) {
    return NextResponse.json({ error: failure.error.message }, { status: 500 });
  }

  const rows = statuses.data ?? [];

  return NextResponse.json({
    statuses: rows,
    // Realized P&L is account-wide and repeated on every row, so take it once rather than
    // summing it across symbols and reporting N times the day's actual result.
    realizedPnl: rows[0]?.realized_pnl ?? 0,
    unrealizedPnl: rows.reduce((sum, r) => sum + (r.unrealized_pnl ?? 0), 0),
    cash: rows[0]?.cash ?? null,
    tradingEnabled: controls.data?.trading_enabled ?? true,
    signals: signals.data ?? [],
    trades: trades.data ?? [],
    serverTime: new Date().toISOString(),
  });
}
