"""Which templates render to which documents.

Convention rather than a hand kept list: every ``*.j2`` file under
``docs/templates`` renders to the same relative path under the repository root,
and every one under ``report/templates`` renders under ``report/``. Files whose
name starts with an underscore are partials and are only included.
"""

from __future__ import annotations

from pathlib import Path

from lookahead_render.render import Target

TEMPLATE_ROOTS = (Path("docs/templates"), Path("report/templates"))


def discover(root: Path) -> list[Target]:
    targets: list[Target] = []
    for base in TEMPLATE_ROOTS:
        folder = root / base
        if not folder.exists():
            continue
        for template in sorted(folder.rglob("*.j2")):
            rel = template.relative_to(folder)
            if any(part.startswith("_") for part in rel.parts):
                continue
            output = rel.with_suffix("")
            prefix = Path("report") if base.parts[0] == "report" else Path()
            targets.append(Target(template=rel.as_posix(), output=(prefix / output).as_posix()))
    return targets


def template_roots(root: Path) -> list[Path]:
    return [root / base for base in TEMPLATE_ROOTS if (root / base).exists()]
