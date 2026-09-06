"use client";

import { useCallback, useEffect, useState } from "react";

type Status = {
  symbol: string;
  updated_at: string;
  mode: string | null;
  strategy_name: string | null;
  market_open: boolean | null;
  last_candle_at: string | null;
  last_price: number | null;
  position_qty: number;
  position_avg_price: number | null;
  cash: number | null;
  realized_pnl: number;
  unrealized_pnl: number;
  last_error: string | null;
};

type SignalRow = {
  id: number;
  created_at: string;
  symbol: string;
  signal_type: string;
  reason: string | null;
  price: number | null;
  acted: boolean;
};

type TradeRow = {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  timestamp: string;
};

type LiveData = {
  statuses: Status[];
  realizedPnl: number;
  unrealizedPnl: number;
  cash: number | null;
  tradingEnabled: boolean;
  signals: SignalRow[];
  trades: TradeRow[];
  serverTime: string;
};

/** A heartbeat older than this means the bot is not polling — either stopped or wedged.
 * The bot writes one every polling interval (60s by default), so two missed beats. */
const STALE_AFTER_MS = 3 * 60 * 1000;

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ago(iso: string, now: number) {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  const color = tone === "up" ? "text-emerald-400" : tone === "down" ? "text-red-400" : "";
  return (
    <div className="rounded-lg border border-neutral-800 px-4 py-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className={`mt-1 text-lg font-medium tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

export function LivePanel() {
  const [data, setData] = useState<LiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/live", { cache: "no-store" });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Failed to load");
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    // Fetch once immediately so the panel isn't blank for the first polling interval. The
    // state writes happen after the await, not synchronously during the effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const poll = setInterval(load, 10_000);
    const tick = setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [load]);

  async function toggleTrading() {
    if (!data) return;
    setToggling(true);
    try {
      const res = await fetch("/api/controls", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trading_enabled: !data.tradingEnabled }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Could not change the switch");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the switch");
    } finally {
      setToggling(false);
    }
  }

  if (error && !data) return <p className="text-sm text-red-400">{error}</p>;
  if (!data) return <p className="text-sm text-neutral-500">Loading…</p>;

  const { statuses } = data;
  // The freshest row decides whether the process is alive — a symbol that errored keeps its
  // older timestamp, and judging the whole bot by the stalest one would read as "stopped".
  const newest = statuses.reduce<Status | null>(
    (best, s) => (!best || s.updated_at > best.updated_at ? s : best),
    null
  );
  const running = newest ? now - new Date(newest.updated_at).getTime() < STALE_AFTER_MS : false;
  const total = data.realizedPnl + data.unrealizedPnl;
  const held = statuses.filter((s) => s.position_qty > 0);
  const errored = statuses.filter((s) => s.last_error);

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-neutral-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <span
            className={`h-2.5 w-2.5 rounded-full ${running ? "bg-emerald-400" : "bg-neutral-600"}`}
          />
          <div>
            <div className="font-medium">
              {running ? "Bot running" : "Bot not running"}
              {newest?.mode && (
                <span className="ml-2 rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                  {newest.mode}
                </span>
              )}
            </div>
            <div className="text-xs text-neutral-500">
              {newest
                ? `${newest.strategy_name ?? "—"} · ${statuses.length} symbol${statuses.length === 1 ? "" : "s"} watched, ${held.length} held · heartbeat ${ago(newest.updated_at, now)}`
                : "No heartbeat yet — start the bot with: python -m algosathi.runner"}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={toggleTrading}
          disabled={toggling}
          className={`rounded border px-3 py-1.5 text-sm disabled:opacity-50 ${
            data.tradingEnabled
              ? "border-red-900 text-red-300 hover:bg-red-950"
              : "border-emerald-900 text-emerald-300 hover:bg-emerald-950"
          }`}
        >
          {data.tradingEnabled ? "Stop opening new trades" : "Allow new trades"}
        </button>
      </div>

      {!data.tradingEnabled && (
        <p className="rounded-lg border border-amber-900/60 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
          New entries are paused. Exits still go through, so an open position can always be
          closed.
        </p>
      )}

      {errored.map((s) => (
        <p
          key={s.symbol}
          className="rounded-lg border border-red-900/60 bg-red-950/30 px-4 py-3 text-sm text-red-200"
        >
          <strong>{s.symbol}</strong> — last poll failed: {s.last_error}
        </p>
      ))}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Cash" value={money(data.cash)} />
        <Stat
          label="Realized P&L"
          value={money(data.realizedPnl)}
          tone={data.realizedPnl >= 0 ? "up" : "down"}
        />
        <Stat
          label="Unrealized P&L"
          value={money(data.unrealizedPnl)}
          tone={data.unrealizedPnl >= 0 ? "up" : "down"}
        />
        <Stat label="Total P&L" value={money(total)} tone={total >= 0 ? "up" : "down"} />
      </div>

      <section>
        <h2 className="mb-2 text-sm font-medium text-neutral-300">Symbols</h2>
        {statuses.length === 0 ? (
          <p className="text-sm text-neutral-500">No symbols reporting yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-neutral-800">
            <table className="w-full text-sm">
              <thead className="bg-neutral-900 text-neutral-400">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Symbol</th>
                  <th className="px-4 py-2 text-right font-medium">Last price</th>
                  <th className="px-4 py-2 text-right font-medium">Position</th>
                  <th className="px-4 py-2 text-right font-medium">Unrealized</th>
                  <th className="px-4 py-2 text-right font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {statuses.map((s) => (
                  <tr key={s.symbol} className="border-t border-neutral-800">
                    <td className="px-4 py-2 font-medium">{s.symbol}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(s.last_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {s.position_qty ? (
                        <span className="text-emerald-400">
                          {s.position_qty} @ {money(s.position_avg_price)}
                        </span>
                      ) : (
                        <span className="text-neutral-500">Flat</span>
                      )}
                    </td>
                    <td
                      className={`px-4 py-2 text-right tabular-nums ${
                        s.unrealized_pnl > 0
                          ? "text-emerald-400"
                          : s.unrealized_pnl < 0
                            ? "text-red-400"
                            : ""
                      }`}
                    >
                      {s.position_qty ? money(s.unrealized_pnl) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right text-xs text-neutral-500">
                      {ago(s.updated_at, now)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-300">Recent signals</h2>
          {data.signals.length === 0 ? (
            <p className="text-sm text-neutral-500">
              Nothing yet. Signals appear here the moment the strategy fires one, whether or not
              risk let it through.
            </p>
          ) : (
            <ul className="space-y-2">
              {data.signals.map((s) => (
                <li key={s.id} className="rounded-lg border border-neutral-800 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={
                        s.signal_type === "buy" ? "text-emerald-400" : "text-amber-400"
                      }
                    >
                      {s.signal_type.toUpperCase()}
                      {!s.acted && (
                        <span className="ml-2 text-xs text-neutral-500">(not acted on)</span>
                      )}
                    </span>
                    <span className="text-xs text-neutral-500">{ago(s.created_at, now)}</span>
                  </div>
                  {s.reason && <p className="mt-1 text-xs text-neutral-400">{s.reason}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-neutral-300">Recent fills</h2>
          {data.trades.length === 0 ? (
            <p className="text-sm text-neutral-500">No fills yet.</p>
          ) : (
            <ul className="space-y-2">
              {data.trades.map((t) => (
                <li
                  key={t.id}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 px-3 py-2 text-sm"
                >
                  <span className={t.side === "buy" ? "text-emerald-400" : "text-amber-400"}>
                    {t.side.toUpperCase()} {t.quantity} {t.symbol}
                  </span>
                  <span className="tabular-nums">{money(t.price)}</span>
                  <span className="text-xs text-neutral-500">{ago(t.timestamp, now)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
