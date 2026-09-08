import json

import pytest

from tests.conftest import TEMPLATE_DIR
from typst_deck.templates import TemplateNotFound, TemplateRegistry


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
