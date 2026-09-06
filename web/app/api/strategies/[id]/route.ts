import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getServiceClient } from "@/lib/supabase-server";

export async function PATCH(
  request: NextRequest,
  ctx: RouteContext<"/api/strategies/[id]">
) {
  const denied = requireAdmin(request);
  if (denied) return denied;

  const { id } = await ctx.params;
  const body = await request.json();
  const supabase = getServiceClient();

  // A running bot loaded its strategy once at startup. Changing which strategy is active
  // while trading is armed would leave the dashboard describing one strategy and the bot
  // trading another, and a restart would silently adopt the swap. Stop trading first.
  const { data: controls } = await supabase
    .from("bot_controls")
    .select("trading_enabled")
    .eq("id", 1)
    .maybeSingle();

  if (controls?.trading_enabled) {
    return NextResponse.json(
      {
        error:
          "Trading is running and the strategy is locked. Stop trading on the Live page " +
          "before changing strategies.",
      },
      { status: 409 }
    );
  }

  if (body?.is_active === true) {
    // Look up the symbol so activating this strategy deactivates any other active
    // strategy for the same symbol (the bot runs at most one active strategy per symbol).
    const { data: current, error: fetchError } = await supabase
      .from("strategies")
      .select("symbol")
      .eq("id", id)
      .maybeSingle();
    if (fetchError) return NextResponse.json({ error: fetchError.message }, { status: 500 });
    if (!current) return NextResponse.json({ error: "Strategy not found" }, { status: 404 });

    const { error: deactivateError } = await supabase
      .from("strategies")
      .update({ is_active: false, updated_at: new Date().toISOString() })
      .eq("symbol", current.symbol)
      .neq("id", id);
    if (deactivateError) {
      return NextResponse.json({ error: deactivateError.message }, { status: 500 });
    }
  }

  const { data, error } = await supabase
    .from("strategies")
    .update({ ...body, updated_at: new Date().toISOString() })
    .eq("id", id)
    .select()
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ error: "Strategy not found" }, { status: 404 });
  return NextResponse.json(data);
}
