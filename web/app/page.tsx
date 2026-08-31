import { equityCurve, summarizeBySymbol } from "@/lib/analytics";
import { fetchTrades } from "@/lib/supabase";
import { EquityChart } from "./equity-chart";
import { Nav } from "./nav";

export const dynamic = "force-dynamic";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-xs uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

export default async function Home() {
  const trades = await fetchTrades();

  if (trades.length === 0) {
    return (
      <main className="mx-auto max-w-5xl flex-1 px-6 py-16">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">AlgoSathi</h1>
          <Nav current="dashboard" />
        </div>
        <p className="mt-4 text-neutral-400">
          No trades recorded yet. Run the bot (paper or live) with Supabase sync configured to
          see activity here.
        </p>
      </main>
    );
  }

  const summary = summarizeBySymbol(trades);
  const curve = equityCurve(trades);
  const totalPnl = summary.reduce((sum, s) => sum + s.realizedPnl, 0);
  const openPositions = summary.filter((s) => s.openQty !== 0);

  return (
    <main className="mx-auto max-w-5xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">AlgoSathi</h1>
        <Nav current="dashboard" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile
          label="Total realized P&L"
          value={totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        />
        <StatTile label="Total trades" value={String(trades.length)} />
        <StatTile label="Open positions" value={String(openPositions.length)} />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-medium text-neutral-400">Per-symbol summary</h2>
        <div className="mt-2 overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-sm">
            <thead className="bg-neutral-900 text-neutral-400">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Symbol</th>
                <th className="px-4 py-2 text-right font-medium">Realized P&L</th>
                <th className="px-4 py-2 text-right font-medium">Open Qty</th>
                <th className="px-4 py-2 text-right font-medium">Avg Price</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((s) => (
                <tr key={s.symbol} className="border-t border-neutral-800">
                  <td className="px-4 py-2">{s.symbol}</td>
                  <td className="px-4 py-2 text-right">{s.realizedPnl.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right">{s.openQty}</td>
                  <td className="px-4 py-2 text-right">{s.avgPrice.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {curve.length > 0 && (
        <section className="mt-8">
          <h2 className="text-sm font-medium text-neutral-400">Realized P&L over time</h2>
          <div className="mt-2 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
            <EquityChart points={curve} />
          </div>
        </section>
      )}

      <section className="mt-8 pb-16">
        <h2 className="text-sm font-medium text-neutral-400">Trade history</h2>
        <div className="mt-2 overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-sm">
            <thead className="bg-neutral-900 text-neutral-400">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Timestamp</th>
                <th className="px-4 py-2 text-left font-medium">Symbol</th>
                <th className="px-4 py-2 text-left font-medium">Side</th>
                <th className="px-4 py-2 text-right font-medium">Qty</th>
                <th className="px-4 py-2 text-right font-medium">Price</th>
                <th className="px-4 py-2 text-left font-medium">Mode</th>
              </tr>
            </thead>
            <tbody>
              {[...trades].reverse().map((t) => (
                <tr key={t.id} className="border-t border-neutral-800">
                  <td className="px-4 py-2">{new Date(t.timestamp).toLocaleString()}</td>
                  <td className="px-4 py-2">{t.symbol}</td>
                  <td className="px-4 py-2 uppercase">{t.side}</td>
                  <td className="px-4 py-2 text-right">{t.quantity}</td>
                  <td className="px-4 py-2 text-right">{t.price.toFixed(2)}</td>
                  <td className="px-4 py-2">{t.mode}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
