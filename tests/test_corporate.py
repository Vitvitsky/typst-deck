"""Общие тесты корпоративных шаблонов: те же проверки для каждого шаблона из
TYPST_DECK_TEST_TEMPLATES. Раньше они были прибиты к templates/lmru-hr; теперь
корпоративный шаблон живёт в репозитории своего канона (docs/template-contract.md).
На этом сервере: TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest
"""
import io
import json

import pytest
from pptx import Presentation

from tests.conftest import CORP_PARAMS, requires_typst
from tests.test_charts import signed_deck
from typst_deck.contract import check_template, filled_slide, SAMPLE_DECK
from typst_deck.model import Deck
from typst_deck.pptx import export_pptx
from typst_deck.render import compile_deck
from typst_deck.slots import check_slide, clamp

MM = 2.83465  # мм в пунктах: зоны заданы в мм, positions отдаёт пункты


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_template_passes_the_full_contract(t, tmp_path):
    assert check_template(t.path, "typst", tmp_path).errors == []


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_declaration_survives_clamp_unchanged(t):
    raw = json.loads((t.path / "template.json").read_text()).get("slots") or {}
    assert clamp(raw, t.id) == raw


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_rejects_the_2026_09_09_incident(t):
    """Переводы строки в подзаголовке титульного слайда сверх объявленного — отказ до рендера."""
    lines = t.slots.get("title", {}).get("subtitle", {}).get("lines")
    if lines is None:
        pytest.skip(f"{t.id}: у подзаголовка титульного слайда не объявлено lines")
    bad = Deck(slides=[{"type": "title", "title": "Итоги",
                        "subtitle": "Лемана" + "\n" * lines + "хвост"}]).slides[0]
    assert check_slide(bad, t.slots, n=1, template_name=t.name)
    ok = Deck(slides=[{"type": "title", "title": "Итоги",
                       "subtitle": "\n".join(["Лемана"] * lines)}]).slides[0]
    assert check_slide(ok, t.slots, n=1, template_name=t.name) == []


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_every_declared_limit_is_enforced(t):
    for stype, fields in t.slots.items():
        for fld, lim in fields.items():
            for key, value in lim.items():
                over = dict(lim)
                over[key] = value + 1
                try:
                    slide = Deck(slides=[filled_slide(stype, {fld: over})]).slides[0]
                except ValueError:
                    continue  # сверх глобального потолка model.py — его держит валидация модели
                assert check_slide(slide, t.slots, n=1, template_name=t.name), f"{stype}.{fld}.{key}"


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_declared_text_fits_its_measured_zone(t, tmp_path):
    """Текст ровно по объявленным пределам не выше зоны, в которой его меряли (measure.json).
    Обрезку внутри слота правило «одна страница» не видит, а этот тест видит."""
    meta = json.loads((t.path / "template.json").read_text())
    if not meta.get("measure"):
        pytest.skip(f"{t.id}: нет measure")
    cfg = json.loads((t.path / meta["measure"]).read_text())
    for i, p in enumerate(cfg["probes"]):
        lim = t.slots.get(p["slide"], {}).get(p["field"])
        if not lim:
            continue
        slide = filled_slide(p["slide"], {p["field"]: lim}, sample=cfg.get("sample", "Итоги квартала "))
        r = compile_deck(Deck(slides=[slide]), tmp_path / f"p{i}", t.path, fonts_dir=t.fonts)
        h = next(x["h"] for x in r.positions if x["field"] == p["field"])
        zone = float(p["height"].removesuffix("mm")) * MM
        assert h <= zone, f"{p['slide']}.{p['field']}: {h:.1f}pt при зоне {zone:.1f}pt"


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_signed_charts_keep_one_page_per_slide(t, deck_dir):
    assert len(compile_deck(signed_deck(), deck_dir, t.path, fonts_dir=t.fonts).svgs) == 2


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_pptx_exports_the_sample_and_declared_limits(t, tmp_path):
    if t.pptx is None:
        pytest.skip(f"{t.id}: нет PowerPoint-мастера")
    declared = Deck(slides=[filled_slide(s, lim) for s, lim in t.slots.items()])
    for deck in (SAMPLE_DECK, declared):
        data = export_pptx(deck, t.path, t.pptx, tmp_path, "typst")
        assert len(Presentation(io.BytesIO(data)).slides) == len(deck.slides)


def test_corp_lemana_tech_has_a_master():
    """Страховка от тихого отката: у канона Lemana Tech мастер обязан быть подключён."""
    lemana = [t for t in (p.values[0] for p in CORP_PARAMS) if t is not None and t.id == "lemana-tech"]
    if not lemana:
        pytest.skip("lemana-tech не подключён в TYPST_DECK_TEST_TEMPLATES")
    assert lemana[0].pptx == "typst-deck/pptx.json"
