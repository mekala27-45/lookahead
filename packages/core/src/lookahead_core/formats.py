"""Number formats shared by the manifest, the renderer and the site bundle.

A figure is stored raw in the manifest with a named format, and every surface
formats it through this module, so the README and the operations review cannot print the
same number two different ways.
"""

from __future__ import annotations

import math
from collections.abc import Callable

FormatFn = Callable[[float | int | str | None], str]


def _num(value: float | int | str | None) -> float:
    if value is None or isinstance(value, str):
        raise TypeError(f"expected a number, got {value!r}")
    return float(value)


def _is_zero(text: str) -> bool:
    return float(text.replace(",", "").lstrip("-")) == 0


def _plain(value: float, decimals: int) -> str:
    text = f"{value:,.{decimals}f}"
    # A value that rounds to zero prints without a sign, whatever its sign before rounding.
    return text[1:] if text.startswith("-") and _is_zero(text) else text


def _signed_money(number: float, body: str, suffix: str = "") -> str:
    sign = "-" if number < 0 and not _is_zero(body) else ""
    return f"{sign}${body}{suffix}"


def fmt_int(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,}"


def _fixed(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        return _plain(_num(value), decimals)

    return inner


def _pct(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        return f"{_plain(_num(value) * 100.0, decimals)}%"

    return inner


def _usd(decimals: int) -> FormatFn:
    def inner(value: float | int | str | None) -> str:
        number = _num(value)
        return _signed_money(number, f"{abs(number):,.{decimals}f}")

    return inner


def fmt_usd_millions(value: float | int | str | None) -> str:
    number = _num(value) / 1_000_000.0
    return _signed_money(number, f"{abs(number):,.1f}", "M")


def fmt_usd_billions(value: float | int | str | None) -> str:
    number = _num(value) / 1_000_000_000.0
    return _signed_money(number, f"{abs(number):,.2f}", "B")


def fmt_bps(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,} bp"


def fmt_signed_pct1(value: float | int | str | None) -> str:
    number = _num(value) * 100.0
    text = _plain(number, 1)
    sign = "+" if number > 0 and not _is_zero(text) else ""
    return f"{sign}{text}%"


def fmt_mw(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,} MW"


def fmt_hours1(value: float | int | str | None) -> str:
    return f"{_plain(_num(value), 1)} h"


def fmt_signed_hours1(value: float | int | str | None) -> str:
    number = _num(value)
    text = _plain(number, 1)
    sign = "+" if number > 0 and not _is_zero(text) else ""
    return f"{sign}{text} h"


def fmt_kwh3(value: float | int | str | None) -> str:
    return f"{_plain(_num(value), 3)} kWh"


def fmt_ms0(value: float | int | str | None) -> str:
    return f"{round(_num(value)):,} ms"


def fmt_text(value: float | int | str | None) -> str:
    if value is None:
        return "not available"
    return str(value)


FORMATS: dict[str, FormatFn] = {
    "int": fmt_int,
    "float1": _fixed(1),
    "float2": _fixed(2),
    "float3": _fixed(3),
    "float4": _fixed(4),
    "pct0": _pct(0),
    "pct1": _pct(1),
    "pct2": _pct(2),
    "pct3": _pct(3),
    "spct1": fmt_signed_pct1,
    "usd0": _usd(0),
    "usd2": _usd(2),
    "usdm": fmt_usd_millions,
    "usdb": fmt_usd_billions,
    "bps": fmt_bps,
    "mw": fmt_mw,
    "hours1": fmt_hours1,
    "shours1": fmt_signed_hours1,
    "kwh3": fmt_kwh3,
    "ms": fmt_ms0,
    "text": fmt_text,
}


def format_value(value: float | int | str | None, fmt: str) -> str:
    if fmt not in FORMATS:
        raise KeyError(f"unknown format {fmt!r}")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "not available"
    if value is None and fmt != "text":
        return "not applicable"
    return FORMATS[fmt](value)
