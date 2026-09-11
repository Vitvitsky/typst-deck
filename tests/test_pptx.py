"""Экспорт в PPTX: сопоставление шаблона и сборка файла на синтетическом мастере."""
import re

import pytest

from tests.conftest import make_pptx_template
from typst_deck.pptx import MappingError, load_mapping, open_master


# --- сопоставление

def check(tdir):
    open_master(tdir, load_mapping(tdir, "pptx.json"))


def test_good_mapping_passes(tmp_path):
    check(make_pptx_template(tmp_path))


BROKEN = {
    "master-outside": (lambda m: m.update(master="../master.pptx"), "внутрь шаблона"),
    "master-missing": (lambda m: m.update(master="nope.pptx"), "нет файла nope.pptx"),
    "unknown-key": (lambda m: m.update(colour="FFFFFF"), "colour"),
    "missing-type": (lambda m: m["slides"].pop("final"), "нет типа final"),
    "missing-ph-field": (lambda m: m["slides"]["title"]["ph"].pop("department"), "нет поля department"),
    "extra-ph-field": (lambda m: m["slides"]["image"]["ph"].update(caption=1), "caption не кладётся"),
    "no-body": (lambda m: m["slides"]["image"].pop("body"), "нет body"),
    "body-on-title": (lambda m: m["slides"]["title"].update(body=[0, 0, 10, 10]), "body у этого типа не бывает"),
    "bad-color": (lambda m: m["chart"].update(negative="red"), "chart.negative"),
    "no-layout": (lambda m: m["slides"]["section"].update(layout="Нет такого"), "нет макета «Нет такого»"),
    "no-idx": (lambda m: m["slides"]["title"]["ph"].update(author=42), "нет заполнителя idx 42"),
    "zone-outside": (lambda m: m["slides"]["chart"].update(body=[600, 80, 200, 260]), "выходит за слайд"),
}


@pytest.mark.parametrize("case", BROKEN)
def test_broken_mapping_is_named(case, tmp_path):
    edit, text = BROKEN[case]
    d = make_pptx_template(tmp_path, mapping_edit=edit)
    with pytest.raises(MappingError, match=re.escape(text)):
        check(d)


def test_unreadable_mapping_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "pptx.json").write_text("{")
    with pytest.raises(MappingError, match="не читается"):
        load_mapping(d, "pptx.json")


def test_mapping_path_stays_inside_the_template(tmp_path):
    d = make_pptx_template(tmp_path)
    with pytest.raises(MappingError, match="внутрь шаблона"):
        load_mapping(d, "../pptx.json")
    with pytest.raises(MappingError, match="нет файла missing.json"):
        load_mapping(d, "missing.json")


def test_broken_master_file_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "master.pptx").write_bytes(b"not a zip")
    with pytest.raises(MappingError, match="не открывается"):
        check(d)
