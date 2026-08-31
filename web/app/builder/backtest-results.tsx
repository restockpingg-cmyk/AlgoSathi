import type { BacktestResult } from "@/lib/backtest";
import { EquityChart } from "../equity-chart";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-xs uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

export function BacktestResults({ result }: { result: BacktestResult }) {
  if (result.totalTrades === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4 text-sm text-neutral-400">
        No trades over this candle history — conditions never fired. Try widening the
        thresholds or check that candle data is synced for this symbol/timeframe.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile
          label="Realized P&L"
          value={result.realizedPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        />
        <StatTile label="Total trades" value={String(result.totalTrades)} />
        <StatTile label="Win rate" value={`${(result.winRate * 100).toFixed(1)}%`} />
        <StatTile label="Max drawdown" value={result.maxDrawdown.toFixed(2)} />
      </div>

      {result.equityCurve.length > 0 && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <EquityChart points={result.equityCurve} />
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-neutral-800">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900 text-neutral-400">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Timestamp</th>
              <th className="px-4 py-2 text-left font-medium">Side</th>
              <th className="px-4 py-2 text-right font-medium">Qty</th>
              <th className="px-4 py-2 text-right font-medium">Price</th>
            </tr>
          </thead>
          <tbody>
            {[...result.trades].reverse().map((t) => (
              <tr key={t.order_id} className="border-t border-neutral-800">
                <td className="px-4 py-2">{new Date(t.timestamp).toLocaleString()}</td>
                <td className="px-4 py-2 uppercase">{t.side}</td>
                <td className="px-4 py-2 text-right">{t.quantity}</td>
                <td className="px-4 py-2 text-right">{t.price.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
