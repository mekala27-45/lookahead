"""The claim gate renders documents from the manifest and diffs whole files."""

from __future__ import annotations

from pathlib import Path

import pytest
from lookahead_core.manifest import Manifest
from lookahead_render.render import ClaimGateError, Renderer, Target, hand_typed_numbers
from lookahead_render.targets import discover


def _setup(tmp_path: Path) -> tuple[Renderer, Path]:
    templates = tmp_path / "docs" / "templates"
    templates.mkdir(parents=True)
    (templates / "RESULTS.md.j2").write_text(
        "# Results\n\nThe MAPE for PJM was {{ v('backtest.own.mape.PJM') }}.\n\n"
        "{{ table('backtest.cross_check') }}\n\n{{ statement() }}\n"
    )
    manifest = Manifest(as_of="2026-09-27", seed=1)
    manifest.put(
        "backtest.own.mape.PJM",
        2.4137,
        "float2",
        source="simulated",
        model="own",
        population="p",
        origin="o",
    )
    manifest.put_table(
        "backtest.cross_check",
        ["Authority", "own", "Operator"],
        ["text", "float2", "float2"],
        [["PJM", 2.41, 2.5]],
        source="simulated",
        model="both",
        population="p",
        origin="o",
    )
    renderer = Renderer(tmp_path, manifest, discover(tmp_path), [templates])
    return renderer, tmp_path / "RESULTS.md"


def test_clean_render_passes(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    assert "2.41" in out.read_text()
    assert "Demand data from the U.S. Energy" in out.read_text()
    assert renderer.check_all() == []


def test_a_number_edited_by_hand_is_caught(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    out.write_text(out.read_text().replace("was 2.41.", "was 2.60."))
    drifts = renderer.check_all()
    assert len(drifts) == 1
    assert "-The MAPE for PJM was 2.60." in drifts[0].diff
    assert "+The MAPE for PJM was 2.41." in drifts[0].diff


def test_a_missing_document_is_caught(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    assert renderer.check_all()[0].output == "RESULTS.md"


def test_refuses_with_no_documents(tmp_path: Path) -> None:
    manifest = Manifest(as_of="2026-09-27", seed=1)
    manifest.put("a.b", 1, "int", source="static", population="p", origin="o")
    with pytest.raises(ClaimGateError, match="no documents"):
        Renderer(tmp_path, manifest, [], [tmp_path])


def test_refuses_with_an_empty_manifest(tmp_path: Path) -> None:
    with pytest.raises(ClaimGateError, match="empty manifest"):
        Renderer(tmp_path, Manifest(as_of="2026-09-27", seed=1), [Target("a.j2", "a.md")], [tmp_path])


def test_unknown_key_fails_loudly(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    (tmp_path / "docs" / "templates" / "RESULTS.md.j2").write_text("{{ v('backtest.nothing') }}")
    with pytest.raises(KeyError):
        renderer.write_all()


def test_hand_typed_numbers_are_found_outside_expressions() -> None:
    text = "Return was {{ v('backtest.mape') }} and the share was 0.81 under CC BY 4.0."
    assert hand_typed_numbers(text, ["CC BY 4.0"]) == ["0.81"]
    assert hand_typed_numbers("{{ v('a.b') }} only", []) == []


def test_partials_are_not_rendered_on_their_own(tmp_path: Path) -> None:
    templates = tmp_path / "report" / "templates" / "cards"
    templates.mkdir(parents=True)
    (templates / "_card.md.j2").write_text("x")
    (templates / "own.md.j2").write_text("{% include 'cards/_card.md.j2' %}")
    targets = discover(tmp_path)
    assert [t.output for t in targets] == ["report/cards/own.md"]


def test_table_html_right_aligns_numbers(tmp_path: Path) -> None:
    from lookahead_render.render import table_html

    renderer, _ = _setup(tmp_path)
    html = table_html(renderer.manifest, "backtest.cross_check")
    assert '<td class="num">2.41</td>' in html
    assert '<th class="txt">Authority</th>' in html
