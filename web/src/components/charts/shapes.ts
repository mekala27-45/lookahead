// Mark geometry shared by the charts: data ends are rounded at 4px, baselines stay square.

/** A diamond centered on (cx, cy); hollow and in ink, it marks the simulated truth. */
export function diamondPath(cx: number, cy: number, r = 6): string {
  return `M${cx},${cy - r}L${cx + r},${cy}L${cx},${cy + r}L${cx - r},${cy}Z`;
}

/** A horizontal bar from its baseline x0 to its data end x1, rounded only at the data end. */
export function hbarPath(x0: number, x1: number, y: number, h: number, radius = 4): string {
  const len = Math.abs(x1 - x0);
  if (len < 0.75) return `M${x0},${y}h0.75v${h}h-0.75Z`;
  const r = Math.min(radius, len, h / 2);
  if (x1 >= x0) {
    return `M${x0},${y}H${x1 - r}A${r},${r} 0 0 1 ${x1},${y + r}V${y + h - r}A${r},${r} 0 0 1 ${x1 - r},${y + h}H${x0}Z`;
  }
  return `M${x0},${y}H${x1 + r}A${r},${r} 0 0 0 ${x1},${y + r}V${y + h - r}A${r},${r} 0 0 0 ${x1 + r},${y + h}H${x0}Z`;
}

/** A vertical bar from its baseline y0 to its data end y1, rounded only at the data end. */
export function vbarPath(x: number, w: number, y0: number, y1: number, radius = 4): string {
  const len = Math.abs(y0 - y1);
  if (len < 0.75) return `M${x},${y0}h${w}v-0.75h${-w}Z`;
  const r = Math.min(radius, len, w / 2);
  if (y1 <= y0) {
    return `M${x},${y0}V${y1 + r}A${r},${r} 0 0 1 ${x + r},${y1}H${x + w - r}A${r},${r} 0 0 1 ${x + w},${y1 + r}V${y0}Z`;
  }
  return `M${x},${y0}V${y1 - r}A${r},${r} 0 0 0 ${x + r},${y1}H${x + w - r}A${r},${r} 0 0 0 ${x + w},${y1 - r}V${y0}Z`;
}

/** Split a label into at most two lines of roughly `chars` characters, at word boundaries. */
export function wrapLabel(text: string, chars: number): string[] {
  if (text.length <= chars) return [text];
  const words = text.split(" ");
  let first = "";
  let i = 0;
  while (i < words.length && `${first} ${words[i]}`.trim().length <= chars) {
    first = `${first} ${words[i]}`.trim();
    i += 1;
  }
  if (!first) return [text];
  return [first, words.slice(i).join(" ")];
}
