"use client";

import { useState } from "react";
import type { StrategyRow } from "@/lib/supabase";

export function StrategyList({ initial }: { initial: StrategyRow[] }) {
  const [strategies, setStrategies] = useState(initial);
  const [pendingId, setPendingId] = useState<number | null>(null);

  async function toggleActive(row: StrategyRow) {
    setPendingId(row.id);
    try {
      const res = await fetch(`/api/strategies/${row.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !row.is_active }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? "Update failed");

      setStrategies((prev) =>
        prev.map((s) => {
          if (s.id === row.id) return { ...s, is_active: !row.is_active };
          if (s.symbol === row.symbol && !row.is_active) return { ...s, is_active: false };
          return s;
        })
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : "Update failed");
    } finally {
      setPendingId(null);
    }
  }

  if (strategies.length === 0) {
    return (
      <p className="text-sm text-neutral-400">
        No strategies saved yet. Build one on the Strategy Builder page.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-800">
      <table className="w-full text-sm">
        <thead className="bg-neutral-900 text-neutral-400">
          <tr>
            <th className="px-4 py-2 text-left font-medium">Name</th>
            <th className="px-4 py-2 text-left font-medium">Symbol</th>
            <th className="px-4 py-2 text-right font-medium">Timeframe</th>
            <th className="px-4 py-2 text-left font-medium">Created</th>
            <th className="px-4 py-2 text-left font-medium">Status</th>
            <th className="px-4 py-2 text-right font-medium">Action</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => (
            <tr key={s.id} className="border-t border-neutral-800">
              <td className="px-4 py-2">{s.name}</td>
              <td className="px-4 py-2">{s.symbol}</td>
              <td className="px-4 py-2 text-right">{s.timeframe_minutes}m</td>
              <td className="px-4 py-2">{new Date(s.created_at).toLocaleDateString()}</td>
              <td className="px-4 py-2">
                {s.is_active ? (
                  <span className="rounded bg-emerald-900/50 px-2 py-0.5 text-xs text-emerald-300">
                    Active
                  </span>
                ) : (
                  <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                    Inactive
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-right">
                <button
                  type="button"
                  disabled={pendingId === s.id}
                  onClick={() => toggleActive(s)}
                  className="rounded border border-neutral-700 px-3 py-1 text-xs hover:bg-neutral-800 disabled:opacity-50"
                >
                  {s.is_active ? "Deactivate" : "Activate"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
