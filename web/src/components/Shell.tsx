import Link from "next/link";
import type { ReactNode } from "react";

import { bundle } from "@/lib/load";
import { REPO } from "@/lib/site";

import { ChartDefs } from "./charts/Defs";
import { NavLinks } from "./NavLinks";
import { ThemeToggle } from "./ThemeToggle";

export function Shell({ children }: { children: ReactNode }) {
  const b = bundle();
  return (
    <div className="min-h-screen flex flex-col">
      <ChartDefs />
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 bg-raised px-3 py-2 rounded"
      >
        Skip to the content
      </a>
      <header className="no-print border-b border-hairline bg-surface">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <Link href="/" className="flex items-baseline gap-2 shrink-0 no-underline" aria-label="lookahead, the control room">
            <span className="font-display text-2xl leading-none font-semibold">lookahead</span>
            <span className="text-xs text-ink2">as of {b.as_of}, {b.served_backend} served</span>
          </Link>
          <nav aria-label="Pages" className="order-3 w-full md:order-none md:w-auto md:flex-1">
            <NavLinks />
          </nav>
          <div className="ml-auto md:ml-0">
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main id="content" className="flex-1 mx-auto w-full max-w-[1200px] px-4 sm:px-6 py-8">
        {children}
      </main>
      <footer className="border-t border-hairline mt-12" data-testid="footer">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6 py-6 text-sm text-ink2 space-y-2">
          <p className="prose text-ink" data-statement>
            {b.statement}
          </p>
          <p className="no-print text-xs">
            Built by Ajay Mekala.{" "}
            <a className="underline" href={REPO}>
              Source on GitHub
            </a>
            , Apache 2.0. Every figure on these pages is read from the published manifest or queried from its marts in your browser;
            the weather the models saw is observed weather, which a real day ahead forecast does not have.
          </p>
        </div>
      </footer>
    </div>
  );
}
