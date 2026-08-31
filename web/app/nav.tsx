import Link from "next/link";

export function Nav({ current }: { current: "dashboard" | "builder" | "strategies" }) {
  const links = [
    { href: "/", label: "Dashboard", key: "dashboard" as const },
    { href: "/builder", label: "Strategy Builder", key: "builder" as const },
    { href: "/strategies", label: "Strategies", key: "strategies" as const },
  ].filter((l) => l.key !== current);

  return (
    <nav className="flex gap-4 text-sm text-neutral-400">
      {links.map((l) => (
        <Link key={l.key} href={l.href} className="hover:text-neutral-100">
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
