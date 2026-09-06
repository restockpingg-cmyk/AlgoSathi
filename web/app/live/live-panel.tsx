"use client";

import { useCallback, useEffect, useState } from "react";

type Status = {
  symbol: string;
  updated_at: string;
  mode: string | null;
  strategy_name: string | null;
  market_open: boolean | null;
  last_price: number | null;
  position_qty: number;
  position_avg_price: number | null;
  invested: number | null;
  stop_price: number | null;
  target_price: number | null;
  trailing_stop_price: number | null;
  high_water_price: number | null;
  unrealized_pnl: number;
  last_error: string | null;
};

type SignalRow = {
  id: number;
  created_at: string;
  symbol: string;
  signal_type: string;
  reason: string | null;
  acted: boolean;
};

type TradeRow = {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  timestamp: string;
  charges: number | null;
};

type LiveData = {
  statuses: Status[];
  realizedPnl: number;
  grossRealizedPnl: number;
  charges: number;
  unrealizedPnl: number;
  cash: number | null;
  tradingEnabled: boolean;
  lockedStrategyId: number | null;
  activeStrategy: { id: number; name: string; symbol: string } | null;
  signals: SignalRow[];
  trades: TradeRow[];
};

/** Two missed heartbeats. The bot writes one every polling interval (60s by default), so
 * anything older than this means the process is not running, not that it is idle. */
const STALE_AFTER_MS = 3 * 60 * 1000;

const money = (v: number | null | undefined, dp = 2) =>
  v == null
    ? "—"
    : v.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp });

const signed = (v: number) => `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`;

function ago(iso: string, now: number) {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

const tone = (v: number) => (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-ink");

/** Where the price sits between the stop and the target.
 *
 * A position is really four numbers — what you paid, what it is worth, where you get out at a
 * loss, and where you take the profit — and their *ordering* is what tells you whether you are
 * in trouble. A table of four figures makes you do that comparison in your head; a scale does
 * it for you. This is the one place the page spends its ink.
 */
function PriceLadder({ s }: { s: Status }) {
  const entry = s.position_avg_price ?? 0;
  const price = s.last_price ?? entry;
  // The live stop is whichever sits higher: the trailing one once it has climbed above the
  // fixed one, otherwise the fixed one.
  const stop = Math.max(s.stop_price ?? 0, s.trailing_stop_price ?? 0) || null;
  const target = s.target_price;

  const floor = Math.min(stop ?? price, price, entry) * 0.999;
  const ceiling = Math.max(target ?? price, price, entry, s.high_water_price ?? 0) * 1.001;
  const span = Math.max(ceiling - floor, 1e-6);
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - floor) / span) * 100))}%`;

  const marks: { value: number; label: string; kind: "stop" | "entry" | "target" }[] = [];
  if (stop) marks.push({ value: stop, label: "Stop", kind: "stop" });
  marks.push({ value: entry, label: "Entry", kind: "entry" });
  if (target) marks.push({ value: target, label: "Target", kind: "target" });

  return (
    <div className="mt-5">
      <div className="relative h-2 rounded-full bg-line">
        {stop && (
          <div
            className="absolute inset-y-0 rounded-full bg-accent-wash"
            style={{ left: pos(stop), right: 0 }}
          />
        )}
        {marks.map((m) => (
          <div
            key={m.label}
            className={`absolute top-1/2 h-4 w-0.5 -translate-y-1/2 ${
              m.kind === "stop" ? "bg-down" : m.kind === "target" ? "bg-up" : "bg-ink-faint"
            }`}
            style={{ left: pos(m.value) }}
          />
        ))}
        <div
          className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-accent shadow-[0_1px_5px_rgba(13,21,51,0.4)]"
          style={{ left: pos(price) }}
          aria-label={`Current price ${money(price)}`}
        />
      </div>

      {/* A legend, not a scale. Marks sit at their real price, which routinely puts the stop
          and the entry within a couple of percent of each other — labels placed under them
          would collide, and labels spread evenly instead would point at the wrong marks. The
          bar carries the position; this only decodes the colours. */}
      <dl className="mt-3.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
        {marks.map((m) => (
          <div key={m.label} className="flex items-baseline gap-1.5">
            <span
              className={`h-1.5 w-1.5 shrink-0 translate-y-[-1px] rounded-full ${
                m.kind === "stop" ? "bg-down" : m.kind === "target" ? "bg-up" : "bg-ink-faint"
              }`}
              aria-hidden
            />
            <dt className="text-[11px] text-ink-faint">{m.label}</dt>
            <dd
              className={`num text-sm font-semibold ${
                m.kind === "stop" ? "text-down" : m.kind === "target" ? "text-up" : "text-ink"
              }`}
            >
              {money(m.value)}
            </dd>
          </div>
        ))}
      </dl>

      {s.trailing_stop_price != null && (
        <p className="mt-3 border-t border-line pt-3 text-xs text-ink-soft">
          Trailing stop <span className="num font-semibold text-ink">{money(s.trailing_stop_price)}</span>
          {s.high_water_price != null && (
            <>
              {" · high since entry "}
              <span className="num font-semibold text-ink">{money(s.high_water_price)}</span>
            </>
          )}
        </p>
      )}
    </div>
  );
}

function PositionCard({ s, now }: { s: Status; now: number }) {
  const pnl = s.unrealized_pnl ?? 0;
  const pct = s.invested ? (pnl / s.invested) * 100 : 0;

  return (
    <article className="rounded-2xl border border-line bg-card p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold tracking-tight">{s.symbol}</h3>
          <p className="num mt-1 text-sm text-ink-soft">
            {s.position_qty} @ {money(s.position_avg_price)} · {money(s.invested, 0)} invested
          </p>
        </div>
        <div className="text-right">
          <p className={`num text-2xl font-bold tracking-tight ${tone(pnl)}`}>{signed(pnl)}</p>
          <p className={`num text-xs font-semibold ${tone(pnl)}`}>
            {pct >= 0 ? "+" : "−"}
            {Math.abs(pct).toFixed(2)}%
          </p>
        </div>
      </header>

      <p className="mt-4 text-sm text-ink-soft">
        Now trading at <span className="num text-base font-bold text-ink">{money(s.last_price)}</span>
      </p>

      <PriceLadder s={s} />

      <p className="mt-3 text-[11px] text-ink-faint">Updated {ago(s.updated_at, now)}</p>
    </article>
  );
}

export function LivePanel() {
  const [data, setData] = useState<LiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);

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
    setBusy(true);
    try {
      const res = await fetch("/api/controls", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trading_enabled: !data.tradingEnabled }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Could not change trading");
      setError(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change trading");
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) return <p className="text-sm text-down">{error}</p>;
  if (!data) return <p className="text-sm text-ink-faint">Loading…</p>;

  const { statuses } = data;
  // The freshest row decides liveness: a symbol that errored keeps an older timestamp, and
  // judging the whole bot by the stalest one would read as "stopped".
  const newest = statuses.reduce<Status | null>(
    (best, s) => (!best || s.updated_at > best.updated_at ? s : best),
    null
  );
  const online = newest ? now - new Date(newest.updated_at).getTime() < STALE_AFTER_MS : false;
  const held = statuses.filter((s) => s.position_qty > 0);
  const flat = statuses.filter((s) => s.position_qty <= 0);
  const errored = statuses.filter((s) => s.last_error);
  const total = data.realizedPnl + data.unrealizedPnl;

  return (
    <div className="space-y-8">
      {error && (
        <p className="rounded-xl border border-down/30 bg-down-wash px-4 py-3 text-sm text-down">
          {error}
        </p>
      )}

      {/* One anchor for the page. Status, the day's result and the only control that matters
          belong together — split across separate cards they read as three equal facts, when
          they actually answer one question: is this running, and is it making money. */}
      <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-[0_1px_2px_rgba(13,21,51,0.04),0_16px_40px_-20px_rgba(47,63,232,0.22)]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-6 py-3.5 text-sm">
          <span className="flex items-center gap-2 font-semibold">
            <span
              className={`h-2 w-2 rounded-full ${online ? "bg-up" : "bg-ink-faint"}`}
              aria-hidden
            />
            {online ? "Online" : "Offline"}
          </span>
          {newest?.mode && (
            <span className="rounded-full bg-accent-wash px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider text-accent-deep">
              {newest.mode}
            </span>
          )}
          <span className="text-ink-soft">{data.activeStrategy?.name ?? "No strategy active"}</span>
          {data.tradingEnabled && data.lockedStrategyId != null && (
            <span className="rounded-full bg-warn-wash px-2.5 py-0.5 text-xs font-semibold text-warn">
              Locked
            </span>
          )}
          <span className="ml-auto text-xs text-ink-faint">
            {online
              ? `${statuses.length} watched · ${held.length} held · ${ago(newest!.updated_at, now)}`
              : "no heartbeat"}
          </span>
        </div>

        <div className="flex flex-col gap-6 px-6 py-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-medium text-ink-soft">Today, after charges</p>
            <p
              className={`num mt-1.5 text-6xl font-bold leading-none tracking-tighter ${tone(
                data.realizedPnl
              )}`}
            >
              {signed(data.realizedPnl)}
            </p>
            <p className="mt-3.5 text-sm text-ink-soft">
              <span className="num font-semibold text-ink">{signed(data.grossRealizedPnl)}</span>{" "}
              before charges of{" "}
              <span className="num font-semibold text-ink">{money(data.charges)}</span>
            </p>
          </div>

          <button
            type="button"
            onClick={toggleTrading}
            disabled={busy}
            className={`w-full shrink-0 rounded-2xl px-8 py-4 text-base font-semibold text-white shadow-sm transition disabled:opacity-50 sm:w-auto ${
              data.tradingEnabled ? "bg-down hover:brightness-95" : "bg-accent hover:brightness-110"
            }`}
          >
            {busy ? "Working…" : data.tradingEnabled ? "Stop trading" : "Start trading"}
          </button>
        </div>

        <dl className="grid grid-cols-3 divide-x divide-line border-t border-line text-center">
          {[
            { label: "Open", value: signed(data.unrealizedPnl), cls: tone(data.unrealizedPnl) },
            { label: "Total", value: signed(total), cls: tone(total) },
            { label: "Cash", value: money(data.cash), cls: "text-ink" },
          ].map((cell) => (
            <div key={cell.label} className="px-3 py-4">
              <dt className="text-xs text-ink-faint">{cell.label}</dt>
              <dd className={`num mt-1 text-lg font-semibold ${cell.cls}`}>{cell.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {!online && (
        <p className="rounded-2xl border border-line bg-card px-5 py-4 text-sm text-ink-soft">
          {data.tradingEnabled ? (
            <>
              <strong className="text-warn">Trading is armed but nothing is reporting.</strong>{" "}
              Nothing will trade until the bot is running on your machine.
            </>
          ) : (
            <>
              Start the bot on your machine to see it here:{" "}
              <code className="rounded bg-surface px-1.5 py-0.5 text-[13px]">
                python -m algosathi.runner
              </code>
            </>
          )}
        </p>
      )}

      {errored.map((s) => (
        <p
          key={s.symbol}
          className="rounded-2xl border border-down/30 bg-down-wash px-5 py-4 text-sm text-down"
        >
          <strong>{s.symbol}</strong> — {s.last_error}
        </p>
      ))}

      <section>
        <h2 className="mb-3 text-base font-semibold tracking-tight">
          Positions {held.length > 0 && <span className="text-ink-faint">({held.length})</span>}
        </h2>
        {held.length === 0 ? (
          <p className="rounded-2xl border border-line bg-card px-5 py-8 text-center text-sm text-ink-soft">
            Nothing held right now.
            <span className="mt-1 block text-xs text-ink-faint">
              Positions appear here with their stop and target the moment the strategy buys.
            </span>
          </p>
        ) : (
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(340px,1fr))]">
            {held.map((s) => (
              <PositionCard key={s.symbol} s={s} now={now} />
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {flat.length > 0 && (
          <section>
            <h2 className="mb-3 text-base font-semibold tracking-tight">
              Watching <span className="text-ink-faint">({flat.length})</span>
            </h2>
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
              {flat.map((s) => (
                <li key={s.symbol} className="flex items-center justify-between px-5 py-3">
                  <span className="text-sm font-medium">{s.symbol}</span>
                  <span className="num text-ink-soft">{money(s.last_price)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h2 className="mb-3 text-base font-semibold tracking-tight">Recent fills</h2>
          {data.trades.length === 0 ? (
            <p className="rounded-2xl border border-line bg-card px-5 py-8 text-center text-sm text-ink-soft">
              No fills yet.
            </p>
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
              {data.trades.slice(0, 8).map((t) => (
                <li key={t.id} className="flex items-center justify-between px-5 py-3">
                  <span className="text-sm">
                    <span
                      className={`font-semibold ${t.side === "buy" ? "text-up" : "text-warn"}`}
                    >
                      {t.side === "buy" ? "Bought" : "Sold"}
                    </span>{" "}
                    {t.quantity} {t.symbol}
                  </span>
                  <span className="text-right">
                    <span className="num block font-semibold">{money(t.price)}</span>
                    {t.charges ? (
                      <span className="block text-[11px] text-ink-faint">
                        fees {money(t.charges)}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section>
        <h2 className="mb-3 text-base font-semibold tracking-tight">Signals</h2>
        {data.signals.length === 0 ? (
          <p className="rounded-2xl border border-line bg-card px-5 py-8 text-center text-sm text-ink-soft">
            Nothing yet.
            <span className="mt-1 block text-xs text-ink-faint">
              Every signal lands here with the reason it fired, whether or not risk let it
              through.
            </span>
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {data.signals.map((s) => (
              <li key={s.id} className="rounded-2xl border border-line bg-card px-5 py-4">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-semibold">
                    <span className={s.signal_type === "buy" ? "text-up" : "text-warn"}>
                      {s.signal_type === "buy" ? "Buy" : "Exit"}
                    </span>{" "}
                    {s.symbol}
                    {!s.acted && (
                      <span className="ml-2 text-xs font-normal text-ink-faint">not acted on</span>
                    )}
                  </span>
                  <span className="text-xs text-ink-faint">{ago(s.created_at, now)}</span>
                </div>
                {s.reason && (
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">{s.reason}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
