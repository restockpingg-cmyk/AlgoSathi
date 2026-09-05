import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getServiceClient } from "@/lib/supabase-server";

export async function GET() {
  const supabase = getServiceClient();
  const { data, error } = await supabase
    .from("strategies")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}

export async function POST(request: NextRequest) {
  const denied = requireAdmin(request);
  if (denied) return denied;

  const body = await request.json();
  const { name, symbol, timeframe_minutes, definition } = body ?? {};

  if (!name || !symbol || !definition) {
    return NextResponse.json(
      { error: "name, symbol, and definition are required" },
      { status: 400 }
    );
  }

  const supabase = getServiceClient();
  const { data, error } = await supabase
    .from("strategies")
    .insert({
      name,
      symbol,
      timeframe_minutes: timeframe_minutes ?? 5,
      definition,
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data, { status: 201 });
}
