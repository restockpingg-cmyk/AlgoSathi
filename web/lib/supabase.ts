import { createClient } from "@supabase/supabase-js";

export type Trade = {
  id: number;
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  timestamp: string;
  mode: string;
};

export function getSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY env vars"
    );
  }
  return createClient(url, key);
}

export async function fetchTrades(): Promise<Trade[]> {
  const supabase = getSupabase();
  const { data, error } = await supabase
    .from("trades")
    .select("*")
    .order("timestamp", { ascending: true });
  if (error) throw error;
  return data ?? [];
}
