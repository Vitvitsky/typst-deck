import json

import pytest

from tests.conftest import TEMPLATE_DIR, requires_typst
from typst_deck.templates import TemplateNotFound, TemplateRegistry, check


def test_registry_lists_default_and_extra(tmp_path):
    extra = tmp_path / "templates" / "dark"
    extra.mkdir(parents=True)
    (extra / "deck.typ").write_text("// stub")
    (extra / "template.json").write_text(json.dumps({"name": "Тёмный", "description": "для вечерних показов"}))
    (tmp_path / "templates" / "broken").mkdir()  # без deck.typ — не шаблон
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    ids = [t.id for t in reg.list()]
    assert ids == ["default", "dark"]
    assert reg.get("dark").name == "Тёмный" and reg.get("default").name == "Корпоративный"
    assert reg.dir_for("dark") == extra
    for bad in ("broken", "../x", "nope"):
        with pytest.raises(TemplateNotFound):
            reg.get(bad)


def test_registry_without_templates_dir():
    reg = TemplateRegistry(TEMPLATE_DIR, TEMPLATE_DIR / "no-such")
    assert [t.id for t in reg.list()] == ["default"]


def test_registry_warns_about_dir_without_deck_typ(tmp_path, caplog):
    (tmp_path / "templates" / "half").mkdir(parents=True)
    with caplog.at_level("WARNING", logger="typst_deck.templates"):
        reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
        reg.list()
        reg.list()
    hits = [r for r in caplog.records if "half" in r.getMessage() and "deck.typ" in r.getMessage()]
    assert len(hits) == 1  # один раз, а не на каждый запрос


def test_registry_several_roots_first_wins(tmp_path):
    for root, name in (("repo", "Репозиторный"), ("private", "Закрытый")):
        d = tmp_path / root / "corp"
        d.mkdir(parents=True)
        (d / "deck.typ").write_text("// stub")
        (d / "template.json").write_text(json.dumps({"name": name}))
    only = tmp_path / "private" / "only-private"
    only.mkdir()
    (only / "deck.typ").write_text("// stub")
    reg = TemplateRegistry(TEMPLATE_DIR, [tmp_path / "repo", tmp_path / "private", tmp_path / "missing"])
    assert [t.id for t in reg.list()] == ["default", "corp", "only-private"]
    assert reg.get("corp").name == "Репозиторный" and reg.dir_for("only-private") == only


def test_registry_skips_template_with_unresolved_import(tmp_path, caplog):
    """Есть deck.typ, но нет того, что он импортирует, — шаблон недосинхронизирован."""
    d = tmp_path / "templates" / "half"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text('#import "slides_template.typ": *\n')
    with caplog.at_level("WARNING", logger="typst_deck.templates"):
        reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert [t.id for t in reg.list()] == ["default"]
    with pytest.raises(TemplateNotFound):
        reg.get("half")
    assert any("slides_template.typ" in r.getMessage() for r in caplog.records)


def test_registry_keeps_template_whose_imports_resolve(tmp_path):
    """@preview и абсолютные пути не проверяются: они разрешаются не относительно шаблона."""
    d = tmp_path / "templates" / "whole"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text(
        '#import "slides_template.typ": *\n#import "@preview/cetz:0.3.4"\n#import "/fields.typ": field\n'
    )
    (d / "slides_template.typ").write_text("// канон")
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert [t.id for t in reg.list()] == ["default", "whole"]


@requires_typst
def test_check_reports_incomplete_template(tmp_path):
    """Реестр шаблон прячет, но сборка образа обязана падать: иначе образ уедет без шаблона."""
    d = tmp_path / "templates" / "half"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text('#import "slides_template.typ": *\n')
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    errors = check(reg, "typst", tmp_path / "work")
    assert any("half" in e and "slides_template.typ" in e for e in errors)


def test_registry_reads_and_clamps_slots(tmp_path):
    d = tmp_path / "templates" / "tight"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({
        "name": "Тесный",
        "slots": {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 300}}},
    }, ensure_ascii=False))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert reg.get("tight").slots == {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 120}}}


def test_registry_resolves_old_ids(tmp_path):
    d = tmp_path / "templates" / "new-id"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "Новый"}))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates", {"old-id": "new-id"})
    assert reg.get("old-id").id == "new-id" and reg.get("old-id").name == "Новый"
    assert reg.dir_for("old-id") == d
    assert [t.id for t in reg.list()] == ["default", "new-id"]  # в списке только действующий id
    assert reg.resolve("old-id") == "new-id" and reg.resolve("other") == "other"


def test_registry_without_slots_declares_nothing(tmp_path):
    """template.json без slots — поведение ровно как сегодня, глобальные пределы."""
    d = tmp_path / "templates" / "plain"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "Простой"}))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    assert reg.get("plain").slots == {} and reg.get("default").slots == {}
    assert reg.get("plain").public() == {"id": "plain", "name": "Простой", "description": ""}


def test_registry_resolves_fonts_dir(tmp_path):
    root = tmp_path / "templates"
    plain = root / "plain"
    (plain / "fonts").mkdir(parents=True)
    (plain / "deck.typ").write_text("// stub")
    custom = root / "custom"
    (custom / "typst-deck" / "fonts").mkdir(parents=True)
    (custom / "deck.typ").write_text("// stub")
    (custom / "template.json").write_text(json.dumps({"name": "C", "fonts": "typst-deck/fonts"}))
    bare = root / "bare"
    bare.mkdir()
    (bare / "deck.typ").write_text("// stub")
    reg = TemplateRegistry(TEMPLATE_DIR, root)
    assert reg.get("plain").fonts == plain / "fonts"
    assert reg.get("custom").fonts == custom / "typst-deck" / "fonts"
    assert reg.get("bare").fonts is None


def test_registry_refuses_fonts_outside_the_template(tmp_path, caplog):
    d = tmp_path / "templates" / "escape"
    (d / "fonts").mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "E", "fonts": "../../elsewhere"}))
    with caplog.at_level("WARNING", logger="typst_deck.templates"):
        reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
        assert reg.get("escape").fonts == d / "fonts"  # взят каталог по умолчанию
    assert any("fonts" in r.getMessage() and "внутрь шаблона" in r.getMessage() for r in caplog.records)
