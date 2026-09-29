"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export const THEME_KEY = "lookahead-theme";

// Dark is the control room's default; light is a full theme the reader chooses, and the one the
// report page and the print stylesheet use.
function current(): Theme {
  const set = document.documentElement.getAttribute("data-theme");
  if (set === "light" || set === "dark") return set;
  return "dark";
}

export function ThemeToggle() {
  // Dark until mounted: the server renders one markup for everyone, and the theme script has
  // already set the real theme on <html> before first paint.
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(current());
  }, []);

  const flip = () => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Blocked storage or a private window: the choice lasts for this page only.
    }
  };

  const other = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={flip}
      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 border border-hairline rounded text-ink2 hover:text-ink hover:border-control shrink-0"
      aria-label={`Switch to the ${other} theme`}
      data-testid="theme-toggle"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" />
      </svg>
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}

/** Runs first in <body>, before anything paints: a stored choice wins; otherwise the control room
 * is dark and the report is light. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark"){t=/\/report\/?$/.test(location.pathname)?"light":"dark";}document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","dark");}})();`;
