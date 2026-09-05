import Link from "next/link";
import { LockControl } from "./lock-control";

export function Nav({
  current,
}: {
  current: "dashboard" | "live" | "builder" | "strategies";
}) {
  const links = [
    { href: "/", label: "Dashboard", key: "dashboard" as const },
    { href: "/live", label: "Live", key: "live" as const },
    { href: "/builder", label: "Strategy Builder", key: "builder" as const },
    { href: "/strategies", label: "Strategies", key: "strategies" as const },
  ].filter((l) => l.key !== current);

  return (
    <nav className="flex flex-wrap items-center gap-4 text-sm text-neutral-400">
      {links.map((l) => (
        <Link key={l.key} href={l.href} className="hover:text-neutral-100">
          {l.label}
        </Link>
      ))}
      <LockControl />
    </nav>
  );
}
