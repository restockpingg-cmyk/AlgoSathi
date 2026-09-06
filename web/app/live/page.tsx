import { Nav } from "../nav";
import { LivePanel } from "./live-panel";

export const dynamic = "force-dynamic";

export default function LivePage() {
  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Live</h1>
        <Nav current="live" />
      </div>
      <p className="mt-1 text-sm text-ink-soft">
        The bot runs on your own machine. This page watches it and can start or stop trading.
      </p>

      <div className="mt-6">
        <LivePanel />
      </div>
    </main>
  );
}
