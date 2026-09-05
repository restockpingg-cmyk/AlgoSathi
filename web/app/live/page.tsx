import { Nav } from "../nav";
import { LivePanel } from "./live-panel";

export const dynamic = "force-dynamic";

export default function LivePage() {
  return (
    <main className="mx-auto max-w-5xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Live</h1>
        <Nav current="live" />
      </div>
      <p className="mt-2 text-sm text-neutral-400">
        What the bot is doing right now, refreshed every 10 seconds. The bot runs on your own
        machine — this page watches it through Supabase and can stop it from opening new
        positions.
      </p>

      <div className="mt-6">
        <LivePanel />
      </div>
    </main>
  );
}
