import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getServiceClient } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/** The kill switch. Admin-only: this decides whether the bot may open new positions. */
export async function PATCH(request: NextRequest) {
  const denied = requireAdmin(request);
  if (denied) return denied;

  const body = await request.json().catch(() => null);
  if (typeof body?.trading_enabled !== "boolean") {
    return NextResponse.json({ error: "trading_enabled must be a boolean" }, { status: 400 });
  }

  const supabase = getServiceClient();
  const { data, error } = await supabase
    .from("bot_controls")
    .update({ trading_enabled: body.trading_enabled, updated_at: new Date().toISOString() })
    .eq("id", 1)
    .select()
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}
