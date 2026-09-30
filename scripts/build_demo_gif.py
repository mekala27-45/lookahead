"""The demo recording: the control room's tile map, a click into an authority, the fan chart with
the operator's gold line and the bands, a forecast issued with its id, then the skill table's wins
and losses and the events heatmap with a known event. Ten seconds, tight crop, written to
docs/demo.gif from frames captured with Playwright against the test server (which serves the
build made with `npm run build:e2e`, so the forecast is issued against the mock API).

    uv run python scripts/build_demo_gif.py --base http://127.0.0.1:4173/lookahead
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo.gif"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4173/lookahead")
    parser.add_argument("--authority", default="ERCO")
    parser.add_argument("--chromium", default="/opt/pw-browsers/chromium")
    args = parser.parse_args()
    from PIL import Image
    from playwright.sync_api import sync_playwright

    frames: list[Image.Image] = []
    durations: list[int] = []

    def shot(page: object, hold_ms: int) -> None:
        import io

        png = page.screenshot(clip={"x": 0, "y": 0, "width": 1180, "height": 760})  # type: ignore[attr-defined]
        image = Image.open(io.BytesIO(png)).convert("RGB").resize((885, 570))
        frames.append(image)
        durations.append(hold_ms)

    with sync_playwright() as p:
        launch = {"executable_path": args.chromium} if Path(args.chromium).exists() else {}
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1180, "height": 900}, color_scheme="dark")
        page.goto(f"{args.base}/")
        page.wait_for_function(
            "document.documentElement.getAttribute('data-ready') === 'true'", timeout=60_000
        )
        page.wait_for_timeout(500)
        shot(page, 1500)
        page.locator(f'[data-authority="{args.authority}"]').scroll_into_view_if_needed()
        page.locator(f'[data-authority="{args.authority}"]').hover()
        shot(page, 700)
        page.locator(f'[data-authority="{args.authority}"]').click()
        page.wait_for_function(
            "document.documentElement.getAttribute('data-ready') === 'true'", timeout=60_000
        )
        page.wait_for_timeout(600)
        shot(page, 1600)
        page.get_by_test_id("issue-forecast").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.get_by_test_id("write-token").fill("demo-token")
        page.get_by_test_id("issue-button").click()
        page.get_by_test_id("forecast-id").wait_for(timeout=60_000)
        page.wait_for_timeout(300)
        shot(page, 1600)
        page.goto(f"{args.base}/backtest/")
        page.wait_for_function(
            "document.documentElement.getAttribute('data-ready') === 'true'", timeout=60_000
        )
        page.wait_for_timeout(600)
        shot(page, 1600)
        page.goto(f"{args.base}/events/")
        page.wait_for_function(
            "document.documentElement.getAttribute('data-ready') === 'true'", timeout=60_000
        )
        page.wait_for_timeout(800)
        shot(page, 1800)
        page.get_by_test_id("known-event-window").scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        shot(page, 1200)
        browser.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} with {len(frames)} frames, {sum(durations) / 1000:.1f} seconds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
