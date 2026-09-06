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

const tone = (v: number) => (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-ink-soft");

/** Where the price sits between the stop and the target.
 *
 * A position is really four numbers — what you paid, what it is worth, where you get out at a
 * loss, and where you take the profit — and their *ordering* is what tells you whether you
 * are in trouble. A table of four figures makes you do that comparison in your head; a scale
 * does it for you. This is the one place the dashboard spends its ink.
 */
function PriceLadder({ s }: { s: Status }) {
  const entry = s.position_avg_price ?? 0;
  const price = s.last_price ?? entry;
  // The active stop is whichever sits higher: the trailing one once it has climbed above the
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
    <div className="mt-4">
      <div className="relative h-2 rounded-full bg-line">
        {/* Everything above the stop is capital still at risk but protected. */}
        {stop && (
          <div
            className="absolute inset-y-0 rounded-full bg-accent-wash"
            style={{ left: pos(stop), right: 0 }}
          />
        )}
        {marks.map((m) => (
          <div
            key={m.label}
            className={`absolute top-1/2 h-3.5 w-0.5 -translate-y-1/2 ${
              m.kind === "stop" ? "bg-down" : m.kind === "target" ? "bg-up" : "bg-ink-faint"
            }`}
            style={{ left: pos(m.value) }}
          />
        ))}
        <div
          className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-accent shadow-[0_1px_4px_rgba(13,21,51,0.35)]"
          style={{ left: pos(price) }}
          aria-label={`Current price ${money(price)}`}
        />
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        {marks.map((m) => (
          <div key={m.label}>
            <dt className="text-[11px] font-medium tracking-wide text-ink-faint">{m.label}</dt>
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
        <p className="mt-2 text-xs text-ink-soft">
          Trailing stop at <span className="num font-semibold">{money(s.trailing_stop_price)}</span>
          {s.high_water_price != null && (
            <> · high since entry <span className="num">{money(s.high_water_price)}</span></>
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
    <article className="rounded-2xl border border-line bg-card p-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">{s.symbol}</h3>
          <p className="num mt-0.5 text-sm text-ink-soft">
            {s.position_qty} @ {money(s.position_avg_price)}
          </p>
        </div>
        <div className="text-right">
          <p className={`num text-xl font-bold ${tone(pnl)}`}>{signed(pnl)}</p>
          <p className={`num text-xs font-medium ${tone(pnl)}`}>
            {pct >= 0 ? "+" : "−"}
            {Math.abs(pct).toFixed(2)}%
          </p>
        </div>
      </header>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl bg-surface px-3 py-2">
          <p className="text-[11px] text-ink-faint">Invested</p>
          <p className="num font-semibold">{money(s.invested)}</p>
        </div>
        <div className="rounded-xl bg-surface px-3 py-2">
          <p className="text-[11px] text-ink-faint">Current price</p>
          <p className="num font-semibold">{money(s.last_price)}</p>
        </div>
      </div>

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
    <div className="space-y-5">
      {error && (
        <p className="rounded-xl border border-down/30 bg-down-wash px-4 py-3 text-sm text-down">
          {error}
        </p>
      )}

      {/* Status and the one control that matters, sized for a thumb. */}
      <section className="overflow-hidden rounded-2xl border border-line bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div className="flex items-center gap-3">
            <span
              className={`h-2.5 w-2.5 rounded-full ${online ? "bg-up" : "bg-ink-faint"}`}
              aria-hidden
            />
            <div>
              <p className="font-semibold tracking-tight">
                {online ? "Bot online" : "Bot offline"}
                {newest?.mode && (
                  <span className="ml-2 rounded-full bg-accent-wash px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent-deep">
                    {newest.mode}
                  </span>
                )}
              </p>
              <p className="mt-0.5 text-xs text-ink-soft">
                {online
                  ? `${statuses.length} watched · ${held.length} held · beat ${ago(newest!.updated_at, now)}`
                  : "Start the bot on your machine: python -m algosathi.runner"}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={toggleTrading}
            disabled={busy}
            className={`w-full rounded-xl px-5 py-3 text-sm font-semibold text-white transition disabled:opacity-50 sm:w-auto ${
              data.tradingEnabled ? "bg-down hover:brightness-95" : "bg-accent hover:brightness-110"
            }`}
          >
            {busy ? "Working…" : data.tradingEnabled ? "Stop trading" : "Start trading"}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-line bg-surface px-5 py-3 text-xs">
          <span className="text-ink-faint">Strategy</span>
          <span className="font-semibold">{data.activeStrategy?.name ?? "none active"}</span>
          {data.tradingEnabled && data.lockedStrategyId != null && (
            <span className="rounded-full bg-warn-wash px-2 py-0.5 font-semibold text-warn">
              Locked while trading
            </span>
          )}
        </div>
      </section>

      {!online && data.tradingEnabled && (
        <p className="rounded-xl border border-warn/30 bg-warn-wash px-4 py-3 text-sm text-warn">
          Trading is armed but no bot is reporting. Nothing will trade until the process is
          running on your machine.
        </p>
      )}

      {!data.tradingEnabled && (
        <p className="rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink-soft">
          New entries are paused. Exits still go through, so an open position can always be
          closed.
        </p>
      )}

      {errored.map((s) => (
        <p
          key={s.symbol}
          className="rounded-xl border border-down/30 bg-down-wash px-4 py-3 text-sm text-down"
        >
          <strong>{s.symbol}</strong> — {s.last_error}
        </p>
      ))}

      {/* The two numbers, side by side. Gross is what a free-trading simulation would show; */}
      {/* net is what reaches the account. */}
      <section className="rounded-2xl border border-line bg-card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-ink-faint">
          Today
        </h2>
        <div className="mt-3 grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-ink-soft">After charges</p>
            <p className={`num text-3xl font-bold tracking-tight ${tone(data.realizedPnl)}`}>
              {signed(data.realizedPnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-soft">Before charges</p>
            <p className="num text-3xl font-bold tracking-tight text-ink-soft">
              {signed(data.grossRealizedPnl)}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-line pt-3 text-xs">
          <span className="text-ink-soft">
            Charges <span className="num font-semibold text-down">−{money(data.charges)}</span>
          </span>
          <span className="text-ink-soft">
            Open <span className={`num font-semibold ${tone(data.unrealizedPnl)}`}>{signed(data.unrealizedPnl)}</span>
          </span>
          <span className="text-ink-soft">
            Total <span className={`num font-semibold ${tone(total)}`}>{signed(total)}</span>
          </span>
          <span className="text-ink-soft">
            Cash <span className="num font-semibold text-ink">{money(data.cash)}</span>
          </span>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-ink-faint">
          Positions {held.length > 0 && `(${held.length})`}
        </h2>
        {held.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line bg-card px-4 py-6 text-center text-sm text-ink-soft">
            Nothing held. Positions appear here with their stop and target as soon as the
            strategy buys.
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {held.map((s) => (
              <PositionCard key={s.symbol} s={s} now={now} />
            ))}
          </div>
        )}
      </section>

      {flat.length > 0 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-ink-faint">
            Watching ({flat.length})
          </h2>
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
            {flat.map((s) => (
              <li key={s.symbol} className="flex items-center justify-between px-4 py-3 text-sm">
                <span className="font-medium">{s.symbol}</span>
                <span className="num text-ink-soft">{money(s.last_price)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-ink-faint">
            Signals
          </h2>
          {data.signals.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-line bg-card px-4 py-6 text-center text-sm text-ink-soft">
              Every signal shows up here with its reason, whether or not risk let it through.
            </p>
          ) : (
            <ul className="space-y-2">
              {data.signals.map((s) => (
                <li key={s.id} className="rounded-xl border border-line bg-card px-4 py-3">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="font-semibold">
                      <span className={s.signal_type === "buy" ? "text-up" : "text-warn"}>
                        {s.signal_type.toUpperCase()}
                      </span>{" "}
                      {s.symbol}
                      {!s.acted && (
                        <span className="ml-2 text-xs font-normal text-ink-faint">not acted on</span>
                      )}
                    </span>
                    <span className="text-xs text-ink-faint">{ago(s.created_at, now)}</span>
                  </div>
                  {s.reason && <p className="mt-1 text-xs text-ink-soft">{s.reason}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-ink-faint">
            Fills
          </h2>
          {data.trades.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-line bg-card px-4 py-6 text-center text-sm text-ink-soft">
              No fills yet.
            </p>
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
              {data.trades.map((t) => (
                <li key={t.id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <span className="font-medium">
                    <span className={t.side === "buy" ? "text-up" : "text-warn"}>
                      {t.side.toUpperCase()}
                    </span>{" "}
                    {t.quantity} {t.symbol}
                  </span>
                  <span className="text-right">
                    <span className="num block font-semibold">{money(t.price)}</span>
                    {t.charges ? (
                      <span className="num block text-[11px] text-ink-faint">
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
    </div>
  );
}
