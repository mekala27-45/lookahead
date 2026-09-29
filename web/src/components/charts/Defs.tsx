// Fill patterns shared by every chart on the page, defined once so that an id means the same
// texture everywhere. Texture carries the difference as well as hue, so a series survives
// greyscale printing and color vision deficiency.
export const PATTERN = {
  /** The baseline and last year's mix: the control gray, hatched. */
  baseline: "url(#pat-baseline)",
  /** Laid over a channel's own color to mark an attribution rule rather than a measurement. */
  rule: "url(#pat-rule)",
  /** The placebo distribution: control gray with a finer hatch. */
  placebo: "url(#pat-placebo)",
  /** A shaded window, such as the weeks a lift test ran. */
  window: "url(#pat-window)",
};

export function ChartDefs() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: "absolute" }}>
      <defs>
        <pattern id="pat-baseline" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="var(--control)" opacity="0.22" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--control)" strokeWidth="1.6" opacity="0.75" />
        </pattern>
        <pattern id="pat-rule" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--raised)" strokeWidth="1.8" opacity="0.85" />
        </pattern>
        <pattern id="pat-placebo" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="4" height="4" fill="var(--control)" opacity="0.35" />
          <line x1="0" y1="0" x2="0" y2="4" stroke="var(--control)" strokeWidth="1.2" opacity="0.8" />
        </pattern>
        <pattern id="pat-window" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="var(--seq-1)" opacity="0.14" />
          <line x1="0" y1="0" x2="0" y2="8" stroke="var(--seq-2)" strokeWidth="1" opacity="0.35" />
        </pattern>
      </defs>
    </svg>
  );
}
