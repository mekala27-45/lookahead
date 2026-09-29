import "@fontsource-variable/atkinson-hyperlegible-mono/index.css";
import "@fontsource-variable/atkinson-hyperlegible-next/index.css";
import "@fontsource-variable/space-grotesk/index.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { THEME_SCRIPT } from "@/components/ThemeToggle";
import palette from "@/theme/palette.json";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "lookahead: the control room", template: "%s | lookahead" },
  description:
    "Demand forecasting for the U.S. power grid and the household meter: every balancing authority in the lower 48 forecast out to 48 hours with calibrated quantiles, graded against the operator's own day ahead forecast, reconciled across the hierarchy, watched by an anomaly detector.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: palette.light.surface },
    { media: "(prefers-color-scheme: dark)", color: palette.dark.surface },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The theme script sets data-theme before first paint, so the server markup cannot match it.
    <html lang="en" suppressHydrationWarning>
      <body>
        {/* First in the body, so it runs before anything paints. An explicit <head> in this layout
            let React's hydration cursor stray into the head when script chunks arrived late. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
