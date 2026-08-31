import { Nav } from "../nav";
import { StrategyForm } from "./strategy-form";

export const dynamic = "force-dynamic";

export default function BuilderPage() {
  return (
    <main className="mx-auto max-w-5xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Strategy Builder</h1>
        <Nav current="builder" />
      </div>
      <p className="mt-2 text-sm text-neutral-400">
        Build entry/exit rules from indicators, backtest them against synced candle data, then
        save and activate to run live/paper in the bot.
      </p>

      <div className="mt-6">
        <StrategyForm />
      </div>
    </main>
  );
}
