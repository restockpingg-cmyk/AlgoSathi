import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getServiceClient } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/** Start/stop trading, and pin the strategy while it runs.
 *
 * Starting locks whichever strategy is active at that moment. A running bot loaded its
 * strategy once at startup, so letting the active row change underneath it would leave the
 * dashboard describing one strategy while the bot trades another — and on a restart it would
 * silently pick up something nobody chose deliberately.
 */
export async function PATCH(request: NextRequest) {
  const denied = requireAdmin(request);
  if (denied) return denied;

  const body = await request.json().catch(() => null);
  if (typeof body?.trading_enabled !== "boolean") {
    return NextResponse.json({ error: "trading_enabled must be a boolean" }, { status: 400 });
  }

  const supabase = getServiceClient();
  const starting = body.trading_enabled;

  let lockedStrategyId: number | null = null;
  if (starting) {
    const { data: active, error } = await supabase
      .from("strategies")
      .select("id, name")
      .eq("is_active", true)
      .maybeSingle();

    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    if (!active) {
      return NextResponse.json(
        { error: "No active strategy. Activate one on the Strategies page before starting." },
        { status: 409 }
      );
    }
    lockedStrategyId = active.id;
  }

  const { data, error } = await supabase
    .from("bot_controls")
    .update({
      trading_enabled: starting,
      locked_strategy_id: lockedStrategyId,
      locked_at: starting ? new Date().toISOString() : null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", 1)
    .select()
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}
