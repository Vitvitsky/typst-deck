import json

import pytest

from tests.conftest import TEMPLATE_DIR, requires_typst
from tests.test_render import full_deck
from typst_deck.model import Deck
from typst_deck.render import CompileError, compile_deck

pytestmark = requires_typst


def test_compile_full_deck(deck_dir, png_bytes):
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert r.pdf.exists() and len(r.svgs) == 6
    assert r.warnings == []
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields
    assert ("s000003", "image") in fields and ("s000006", "contact") in fields
    p = next(p for p in r.positions if p["slide"] == "s000003" and p["field"] == "title")
    assert p["page"] == 3 and p["w"] > 0 and p["h"] > 0
    assert json.loads((deck_dir / "build" / "positions.json").read_text()) == r.positions
    assert (deck_dir / "build" / "template").is_symlink()


def test_compile_missing_image_is_warning(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 6 and r.warnings


def test_compile_replaces_previous_build(deck_dir):
    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    r = compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1
    assert not (deck_dir / "build" / "slide-2.svg").exists()
    assert not (deck_dir / "build.tmp").exists()


def test_compile_error_surfaces_stderr(deck_dir, tmp_path):
    bad_tpl = tmp_path / "tpl"
    bad_tpl.mkdir()
    (bad_tpl / "deck.typ").write_text("#let deck(title: none, body) = body\n")
    with pytest.raises(CompileError) as e:
        compile_deck(full_deck(), deck_dir, bad_tpl)
    assert "slide-title" in e.value.stderr


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_every_template_honours_contract(deck_dir, png_bytes, tid):
    """Каждый шаблон в templates/ собирает образец: 6 страниц и позиции полей."""
    from typst_deck.templates import SAMPLE_DECK
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    deck = SAMPLE_DECK.model_copy(deep=True)
    deck.slides[2].image = "a000001.png"
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 6
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields and ("s000006", "title") in fields


def test_compile_reports_per_command_timings(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert set(r.timings) == {"pdf_ms", "svg_ms", "query_ms", "ms"}
    assert all(isinstance(v, int) and v >= 0 for v in r.timings.values())
    assert r.timings["ms"] >= max(r.timings["pdf_ms"], r.timings["svg_ms"], r.timings["query_ms"])


def test_compile_logs_render_done(deck_dir, caplog):
    caplog.set_level("INFO", logger="typst_deck.render")
    deck = full_deck()
    compile_deck(deck, deck_dir, TEMPLATE_DIR)
    rec = next(r for r in caplog.records if r.msg == "render.done")
    assert rec.fields["deck"] == deck.id
    assert rec.fields["slides"] == 6
    assert rec.fields["svg_kb"] > 0
    assert rec.fields["ms"] >= 0


def test_compile_hashes_each_page(deck_dir):
    import json as _json

    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.pages) == 6
    assert all(isinstance(h, str) and h for h in r.pages)
    assert len(set(r.pages)) == 6, "разные слайды — разные хеши"
    assert _json.loads((deck_dir / "build" / "pages.json").read_text()) == r.pages


def test_page_hash_changes_only_for_edited_slide(deck_dir):
    before = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR).pages
    deck = full_deck()
    deck.slides[2].title = "Совсем другой заголовок"
    after = compile_deck(deck, deck_dir, TEMPLATE_DIR).pages
    assert after[2] != before[2], "правленый слайд обязан сменить хеш"
    assert [after[i] for i in (0, 1, 3, 4, 5)] == [before[i] for i in (0, 1, 3, 4, 5)], \
        "остальные слайды должны остаться под теми же URL"
