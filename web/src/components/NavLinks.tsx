"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: [string, string][] = [
  ["/", "Control room"],
  ["/backtest/", "Backtest"],
  ["/hierarchy/", "Hierarchy"],
  ["/events/", "Events"],
  ["/households/", "Households"],
  ["/report/", "Report"],
];

const trim = (path: string) => (path.length > 1 ? path.replace(/\/+$/, "") : path);

export function NavLinks() {
  const here = trim(usePathname() || "/");
  return (
    <ul className="flex flex-wrap gap-x-1 gap-y-1 text-sm">
      {NAV.map(([href, label]) => {
        const active = trim(href) === here;
        return (
          <li key={href}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={`block px-2 py-1 rounded ${active ? "text-ink font-semibold underline decoration-lead decoration-2 underline-offset-[6px]" : "text-ink2 hover:text-ink"}`}
            >
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
