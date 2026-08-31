import { fetchStrategies } from "@/lib/supabase";
import { Nav } from "../nav";
import { StrategyList } from "./strategy-list";

export const dynamic = "force-dynamic";

export default async function StrategiesPage() {
  const strategies = await fetchStrategies();

  return (
    <main className="mx-auto max-w-5xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Strategies</h1>
        <Nav current="strategies" />
      </div>
      <p className="mt-2 text-sm text-neutral-400">
        Activating a strategy deactivates any other active strategy for the same symbol — the
        bot runs whichever is active when <code>strategy.source: supabase</code> is set in
        config/settings.yaml.
      </p>

      <div className="mt-6">
        <StrategyList initial={strategies} />
      </div>
    </main>
  );
}
