"use client";

import { useState } from "react";
import type { BacktestResult } from "@/lib/backtest";
import type { Condition, ConditionGroup, Operand, StrategyDefinition } from "@/lib/rule-engine";
import { BacktestResults } from "./backtest-results";

type IndicatorKey =
  | "close"
  | "open"
  | "high"
  | "low"
  | "sma"
  | "ema"
  | "rsi"
  | "macd_line"
  | "macd_signal"
  | "macd_hist";

const INDICATORS: { key: IndicatorKey; label: string; hasPeriod: boolean; defaultPeriod?: number }[] = [
  { key: "close", label: "Price (Close)", hasPeriod: false },
  { key: "open", label: "Price (Open)", hasPeriod: false },
  { key: "high", label: "Price (High)", hasPeriod: false },
  { key: "low", label: "Price (Low)", hasPeriod: false },
  { key: "sma", label: "SMA", hasPeriod: true, defaultPeriod: 9 },
  { key: "ema", label: "EMA", hasPeriod: true, defaultPeriod: 9 },
  { key: "rsi", label: "RSI", hasPeriod: true, defaultPeriod: 14 },
  { key: "macd_line", label: "MACD Line", hasPeriod: false },
  { key: "macd_signal", label: "MACD Signal", hasPeriod: false },
  { key: "macd_hist", label: "MACD Histogram", hasPeriod: false },
];

const OPERATORS: { key: Condition["op"]; label: string }[] = [
  { key: "crosses_above", label: "crosses above" },
  { key: "crosses_below", label: "crosses below" },
  { key: ">", label: ">" },
  { key: "<", label: "<" },
  { key: ">=", label: ">=" },
  { key: "<=", label: "<=" },
];

function defaultOperand(): Operand {
  return { indicator: "sma", period: 9 };
}

type IndicatorOperand = Exclude<Operand, { value: number }>;

function OperandEditor({
  operand,
  onChange,
}: {
  operand: Operand;
  onChange: (next: Operand) => void;
}) {
  const isConstant = "value" in operand;
  const indicatorKey: IndicatorKey = isConstant ? "sma" : (operand as IndicatorOperand).indicator;
  const spec = INDICATORS.find((i) => i.key === indicatorKey);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm"
        value={isConstant ? "value" : indicatorKey}
        onChange={(e) => {
          const key = e.target.value;
          if (key === "value") {
            onChange({ value: 0 });
          } else {
            const s = INDICATORS.find((i) => i.key === key)!;
            onChange({ indicator: s.key, ...(s.hasPeriod ? { period: s.defaultPeriod } : {}) } as Operand);
          }
        }}
      >
        <option value="value">Constant</option>
        {INDICATORS.map((i) => (
          <option key={i.key} value={i.key}>
            {i.label}
          </option>
        ))}
      </select>

      {isConstant && (
        <input
          type="number"
          className="w-24 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm"
          value={(operand as { value: number }).value}
          onChange={(e) => onChange({ value: Number(e.target.value) })}
        />
      )}

      {!isConstant && spec?.hasPeriod && (
        <input
          type="number"
          min={1}
          className="w-20 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm"
          value={(operand as IndicatorOperand & { period?: number }).period ?? spec.defaultPeriod ?? 14}
          onChange={(e) =>
            onChange({ ...(operand as IndicatorOperand), period: Number(e.target.value) } as Operand)
          }
        />
      )}
    </div>
  );
}

function ConditionRow({
  condition,
  onChange,
  onRemove,
}: {
  condition: Condition;
  onChange: (next: Condition) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-neutral-800 bg-neutral-900/50 p-2">
      <OperandEditor operand={condition.left} onChange={(left) => onChange({ ...condition, left })} />
      <select
        className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm"
        value={condition.op}
        onChange={(e) => onChange({ ...condition, op: e.target.value as Condition["op"] })}
      >
        {OPERATORS.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
      <OperandEditor operand={condition.right} onChange={(right) => onChange({ ...condition, right })} />
      <button
        type="button"
        onClick={onRemove}
        className="ml-auto rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:text-neutral-100"
      >
        Remove
      </button>
    </div>
  );
}

function ConditionGroupEditor({
  title,
  group,
  onChange,
}: {
  title: string;
  group: ConditionGroup;
  onChange: (next: ConditionGroup) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-400">{title}</h3>
        <div className="flex items-center gap-2 text-xs text-neutral-400">
          Match
          <select
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
            value={group.operator}
            onChange={(e) => onChange({ ...group, operator: e.target.value as "and" | "or" })}
          >
            <option value="and">ALL conditions (AND)</option>
            <option value="or">ANY condition (OR)</option>
          </select>
        </div>
      </div>

      <div className="mt-2 flex flex-col gap-2">
        {group.conditions.map((c, i) => (
          <ConditionRow
            key={i}
            condition={c}
            onChange={(next) => {
              const conditions = [...group.conditions];
              conditions[i] = next;
              onChange({ ...group, conditions });
            }}
            onRemove={() => {
              onChange({ ...group, conditions: group.conditions.filter((_, j) => j !== i) });
            }}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={() =>
          onChange({
            ...group,
            conditions: [...group.conditions, { left: defaultOperand(), op: "crosses_above", right: defaultOperand() }],
          })
        }
        className="mt-2 rounded border border-neutral-700 px-3 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
      >
        + Add condition
      </button>
    </div>
  );
}

export function StrategyForm() {
  const [name, setName] = useState("My strategy");
  const [symbol, setSymbol] = useState("INFY");
  const [timeframeMinutes, setTimeframeMinutes] = useState(5);
  const [entry, setEntry] = useState<ConditionGroup>({
    operator: "and",
    conditions: [{ left: { indicator: "sma", period: 9 }, op: "crosses_above", right: { indicator: "sma", period: 21 } }],
  });
  const [exit, setExit] = useState<ConditionGroup>({
    operator: "and",
    conditions: [{ left: { indicator: "sma", period: 9 }, op: "crosses_below", right: { indicator: "sma", period: 21 } }],
  });

  const [result, setResult] = useState<BacktestResult | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const definition: StrategyDefinition = { entry, exit };

  async function runBacktest() {
    setIsBacktesting(true);
    setBacktestError(null);
    setResult(null);
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition, symbol, timeframeMinutes }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Backtest failed");
      setResult(data);
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setIsBacktesting(false);
    }
  }

  async function saveStrategy() {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const res = await fetch("/api/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, symbol, timeframe_minutes: timeframeMinutes, definition }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Save failed");
      setSaveMessage(`Saved "${data.name}". Activate it from the Strategies page to run it live.`);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-sm text-neutral-400">
          Name
          <input
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-neutral-400">
          Symbol
          <input
            className="w-32 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-neutral-400">
          Timeframe
          <select
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100"
            value={timeframeMinutes}
            onChange={(e) => setTimeframeMinutes(Number(e.target.value))}
          >
            {[1, 5, 15, 60].map((m) => (
              <option key={m} value={m}>
                {m}m
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="rounded-lg border border-neutral-800 p-4">
        <ConditionGroupEditor title="Entry (BUY)" group={entry} onChange={setEntry} />
      </div>
      <div className="rounded-lg border border-neutral-800 p-4">
        <ConditionGroupEditor title="Exit" group={exit} onChange={setExit} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={runBacktest}
          disabled={isBacktesting}
          className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {isBacktesting ? "Running backtest…" : "Run Backtest"}
        </button>
        <button
          type="button"
          onClick={saveStrategy}
          disabled={isSaving}
          className="rounded border border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-100 hover:bg-neutral-800 disabled:opacity-50"
        >
          {isSaving ? "Saving…" : "Save Strategy"}
        </button>
        {saveMessage && <span className="text-sm text-neutral-400">{saveMessage}</span>}
      </div>

      {backtestError && (
        <div className="rounded border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">
          {backtestError}
        </div>
      )}

      {result && <BacktestResults result={result} />}
    </div>
  );
}
