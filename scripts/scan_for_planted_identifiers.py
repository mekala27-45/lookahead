"""Scan everything published for a raw data row or an identity that should not be there.

What counts here: a Luhn valid card number, a Social Security number pattern, an
email address, a raw row of the London release (recognised by its header, because
household rows are never committed, only derived tables), the raw EIA header (the
six month files are never committed either), or any token on the planted list in
data/planted_identifiers.txt. The planted list is what the test plants and then
expects the scan to find.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SSN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# A run of digits after a decimal point is the fraction of a number, not a card.
PAN = re.compile(r"(?<![\d.])(?:\d[ -]?){13,19}(?!\d)")
RAW_HEADERS = {
    "london raw header": "LCLid,stdorToU,DateTime,KWH/hh (per half hour)",
    "eia balance raw header": "Balancing Authority,Data Date,Hour Number,Local Time at End of Hour,UTC Time at End of Hour,Demand Forecast (MW),Demand (MW),Net Generation (MW),Total Interchange (MW)",
}
SCAN_GLOBS = (
    "results/**/*.json",
    "results/**/*.csv",
    "results/**/*.parquet",
    "results/**/*.md",
    "data/**/*.csv",
    "data/**/*.parquet",
    "data/**/*.json",
    "data/**/*.md",
    "report/**/*.md",
    "report/**/*.html",
    "docs/**/*.md",
    "README.md",
    "RESULTS.md",
    "web/public/data/**/*",
    "web/out/**/*.html",
    "web/out/**/*.json",
    "logs/**/*.log",
)
PLANTED_FILE = Path("data/planted_identifiers.txt")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "lookahead.example")


def luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        number = int(char)
        if position % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def find_card_numbers(text: str) -> list[str]:
    found: list[str] = []
    for match in PAN.finditer(text):
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and luhn_valid(digits):
            found.append(digits)
    return found


def load_planted(root: Path) -> set[str]:
    path = root / PLANTED_FILE
    if not path.exists():
        return set()
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def text_of(path: Path) -> str:
    if path.suffix == ".parquet":
        import polars as pl

        frame = pl.read_parquet(path)
        parts: list[str] = [",".join(frame.columns)]
        for column, dtype in zip(frame.columns, frame.dtypes, strict=True):
            if dtype == pl.Utf8:
                parts.extend(str(v) for v in frame[column].drop_nulls().to_list())
            elif dtype.is_integer():
                parts.extend(str(v) for v in frame[column].drop_nulls().to_list() if abs(int(v)) >= 10**12)
        return "\n".join(parts)
    if path.suffix == ".json":
        try:
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def findings(text: str, planted: set[str]) -> list[str]:
    out = [f"card number ending {pan[-4:]}" for pan in find_card_numbers(text)]
    out += [f"SSN pattern {m.group(0)[:3]}-XX-XXXX" for m in SSN.finditer(text)]
    for match in EMAIL.finditer(text):
        address = match.group(0)
        if not address.lower().endswith(ALLOWED_EMAIL_DOMAINS):
            out.append(f"email address at {address.split('@')[1]}")
    for name, header in RAW_HEADERS.items():
        if header in text:
            out.append(name)
    if planted:
        lowered = text.lower()
        out.extend(f"planted identifier '{token}'" for token in sorted(planted) if token in lowered)
    return out


def targets(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in SCAN_GLOBS:
        found.extend(
            p
            for p in root.glob(pattern)
            if p.is_file() and "node_modules" not in p.parts and "external" not in p.parts
        )
    return sorted(set(found))


def check(root: Path, files: Iterable[Path] | None = None, planted: set[str] | None = None) -> int:
    scan = list(files) if files is not None else targets(root)
    if not scan:
        raise ValueError("the identifier scan found no files to scan")
    tokens = planted if planted is not None else load_planted(root)
    problems: list[str] = []
    for path in scan:
        if path.name == PLANTED_FILE.name:
            continue
        for finding in findings(text_of(path), tokens):
            problems.append(f"{path.relative_to(root)}: {finding}")
    if problems:
        raise ValueError("identifier scan failed:\n" + "\n".join(problems[:50]))
    return len(scan)


if __name__ == "__main__":
    count = check(Path(__file__).resolve().parents[1])
    print(
        f"identifier scan: {count} files, no card numbers, SSN patterns, addresses, raw rows or planted tokens"
    )
