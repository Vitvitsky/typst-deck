import shutil
from pathlib import Path

import pytest

from tests.conftest import (FALLBACK_FONT, NO_CLIP_FINAL, NO_CONTACT, ROOT, TEMPLATE_DIR, TWO_PAGES,
                            make_template, requires_typst)
from typst_deck.contract import check_template, filled_slide
from typst_deck.model import Deck

DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
needs_dejavu = pytest.mark.skipif(not (DEJAVU / "DejaVuSans.ttf").exists(), reason="нет файлов DejaVu")


@requires_typst
@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, ROOT / "templates" / "dark"], ids=["default", "dark"])
def test_reference_templates_pass_the_full_contract(tdir, tmp_path):
    rep = check_template(tdir, "typst", tmp_path)
    assert rep.errors == [] and rep.warnings == []


@requires_typst
def test_missing_template_json_is_an_error(tmp_path):
    d = make_template(tmp_path, "nojson")
    (d / "template.json").unlink()
    assert any("template.json" in e for e in check_template(d, "typst", tmp_path / "w").errors)


@requires_typst
def test_inapplicable_slots_key_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    d = make_template(tmp_path, "badslots", meta={"name": "Б", "slots": {"title": {"title": {"count": 3}}}})
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any(e.startswith("slots:") for e in full.errors)
    assert start.errors == [] and any(w.startswith("slots:") for w in start.warnings)


@requires_typst
def test_bad_fonts_value_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    """resolve_fonts бросает ValueError на путь наружу шаблона. Реестр в этом же случае
    не падает, а откатывается на fonts/ (templates.py _info) и сервис продолжает отдавать
    шаблон — стартовый режим не должен ломаться там, где сервис не ломается."""
    d = make_template(tmp_path, "badfonts", meta={"name": "Ф", "fonts": "../elsewhere"})
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any("fonts" in e for e in full.errors), full.errors
    assert start.errors == [] and any("fonts" in w for w in start.warnings), start.warnings


@requires_typst
def test_bad_fonts_value_at_start_does_not_stop_the_check(tmp_path):
    """Стартовый режим откатывается на fonts/ и проверяет дальше: правило 2 по-прежнему
    ловит двойную страницу, а не молчит из-за раннего возврата на плохом fonts."""
    d = make_template(tmp_path, "badfontstwopages", deck_edit=TWO_PAGES,
                      meta={"name": "Ф", "fonts": "../elsewhere"})
    start = check_template(d, "typst", tmp_path / "w", full=False)
    assert any("образец не собирается" in e for e in start.errors), start.errors


@requires_typst
def test_extra_page_per_slide_is_an_error(tmp_path):
    d = make_template(tmp_path, "twopages", deck_edit=TWO_PAGES)
    assert any("образец не собирается" in e for e in check_template(d, "typst", tmp_path / "w").errors)


@requires_typst
def test_overflow_on_oversized_or_declared_text_is_an_error(tmp_path):
    """Правила 3 и 5: финальный слайд без обрезки переливается на вторую страницу."""
    d = make_template(tmp_path, "overflow", deck_edit=NO_CLIP_FINAL,
                      meta={"name": "П", "slots": {"final": {"title": {"max": 120},
                                                            "contact": {"max": 120, "lines": 9}}}})
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("переросший текст" in e for e in errors), errors
    assert any("по объявленным пределам" in e for e in errors), errors


@requires_typst
def test_unmarked_field_is_an_error(tmp_path):
    d = make_template(tmp_path, "nocontact", deck_edit=NO_CONTACT)
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("contact" in e and "не размечено" in e for e in errors), errors


@requires_typst
@needs_dejavu
def test_unused_fonts_dir_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    """Каталог шрифтов есть, а шаблон называет другое семейство — случай «…Pro Trl»."""
    d = make_template(tmp_path, "unused", meta={"name": "Н", "fonts": "fonts"})
    (d / "fonts").mkdir()
    shutil.copy(DEJAVU / "DejaVuSansMono.ttf", d / "fonts")
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any("не используются" in e for e in full.errors), full.errors
    assert start.errors == [] and any("не используются" in w for w in start.warnings)


@requires_typst
@needs_dejavu
def test_used_fonts_dir_passes(tmp_path):
    d = make_template(tmp_path, "used", meta={"name": "И", "fonts": "fonts"})
    (d / "fonts").mkdir()
    shutil.copy(DEJAVU / "DejaVuSans.ttf", d / "fonts")
    assert check_template(d, "typst", tmp_path / "w").errors == []


@requires_typst
def test_fallback_font_family_is_only_a_warning(tmp_path):
    """typst предупреждает о каждом запасном семействе; это сведения, не ошибка."""
    d = make_template(tmp_path, "fallback", deck_edit=FALLBACK_FONT)
    rep = check_template(d, "typst", tmp_path / "w")
    assert rep.errors == []
    assert any("нет такого шрифта" in w.lower() for w in rep.warnings), rep.warnings


@requires_typst
def test_cli_checks_one_template_directory(tmp_path, capsys):
    from typst_deck.templates import main

    assert main([str(TEMPLATE_DIR)]) == 0
    assert "контракт соблюдён" in capsys.readouterr().out
    broken = make_template(tmp_path, "twopages", deck_edit=TWO_PAGES)
    assert main([str(broken)]) == 1


def test_filled_slide_respects_limits():
    s = filled_slide("title", {"title": {"max": 70, "lines": 2}, "subtitle": {"max": 65, "lines": 1}})
    assert len(s["title"]) == 70 and s["title"].count("\n") == 1
    assert len(s["subtitle"]) == 65 and "\n" not in s["subtitle"]
    c = filled_slide("chart", {"bullets": {"count": 4, "max": 120}, "labels": {"count": 5}})
    assert len(c["bullets"]) == 4 and all(len(b) == 120 for b in c["bullets"])
    assert all(len(sr["values"]) == len(c["labels"]) == 5 for sr in c["series"])
    Deck(slides=[s, c, filled_slide("bar-chart", {"data": {"count": 6}}), filled_slide("final", {})])
