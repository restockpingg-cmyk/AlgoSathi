"use client";

import { useEffect, useState } from "react";

/** Shows whether this browser can change strategies, and lets the owner unlock it.
 *
 * Viewing is always allowed, so a locked visitor sees the whole dashboard and can still run
 * backtests — the lock only covers saving and activating.
 */
export function LockControl() {
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const [prompting, setPrompting] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/admin-session")
      .then((res) => res.json())
      .then((data) => setUnlocked(Boolean(data.unlocked)))
      .catch(() => setUnlocked(false));
  }, []);

  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/admin-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Unlock failed");
      setUnlocked(true);
      setPrompting(false);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unlock failed");
    } finally {
      setBusy(false);
    }
  }

  async function lock() {
    await fetch("/api/admin-session", { method: "DELETE" });
    setUnlocked(false);
  }

  if (unlocked === null) return null;

  if (unlocked) {
    return (
      <button
        type="button"
        onClick={lock}
        className="text-sm text-emerald-400 hover:text-emerald-300"
        title="You can save and activate strategies"
      >
        Unlocked · lock
      </button>
    );
  }

  if (!prompting) {
    return (
      <button
        type="button"
        onClick={() => setPrompting(true)}
        className="text-sm text-neutral-400 hover:text-neutral-100"
        title="Viewing only — unlock to save or activate strategies"
      >
        View only · unlock
      </button>
    );
  }

  return (
    <form onSubmit={unlock} className="flex items-center gap-2">
      <input
        type="password"
        autoFocus
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Admin password"
        className="w-40 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm"
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded border border-neutral-700 px-2 py-1 text-sm hover:bg-neutral-800 disabled:opacity-50"
      >
        {busy ? "…" : "Unlock"}
      </button>
      <button
        type="button"
        onClick={() => {
          setPrompting(false);
          setError(null);
        }}
        className="text-sm text-neutral-500 hover:text-neutral-300"
      >
        Cancel
      </button>
      {error && <span className="text-sm text-red-400">{error}</span>}
    </form>
  );
}
