"""Перенос сохранённых колод на новые типы слайдов."""
import json
from pathlib import Path

from typst_deck.migrate_slides import migrate, upgrade_slide
from typst_deck.model import Deck

LEGACY = {
    "id": "d1", "title": "Итоги", "template": "default", "version": 3,
    "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
    "slides": [
        {"id": "s000001", "type": "title", "title": "Итоги", "subtitle": "Q3", "notes": "з"},
        {"id": "s000002", "type": "image", "title": "Рост", "bullets": ["раз", "два"],
         "image": None, "image_size": "medium", "caption": "подпись"},
        {"id": "s000003", "type": "image", "title": "Схема", "bullets": [], "image": "a1.png",
         "image_size": "large", "caption": "подпись"},
        {"id": "s000004", "type": "bar-chart", "title": "Диаграмма", "unit": "млн",
         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": -17}], "bullets": ["в"]},
        {"id": "s000005", "type": "chart", "title": "График", "labels": ["Q1", "Q2"],
         "series": [{"name": "Выручка", "values": [1, 2]}], "unit": "", "bullets": []},
        {"id": "s000006", "type": "final", "title": "Спасибо", "contact": "team@corp"},
    ],
}


def write_deck(root: Path, deck_id: str, versions: int = 2) -> Path:
    d = root / "decks" / deck_id
    (d / "versions").mkdir(parents=True)
    raw = json.dumps(LEGACY | {"id": deck_id}, ensure_ascii=False)
    (d / "deck.json").write_text(raw)
    for v in range(1, versions + 1):
        (d / "versions" / f"{v:06d}.json").write_text(raw)
    return d


def test_upgrade_slide_rules():
    old = {}
    for s in LEGACY["slides"]:
        if s["type"] not in old:
            old[s["type"]] = s
    text = upgrade_slide(old["image"] | {"image": None})
    assert text["type"] == "text" and text["bullets"] == ["раз", "два"] and text["id"] == "s000002"
    assert "caption" not in text and "image" not in text and text["notes"] == ""
    picture = upgrade_slide(old["image"] | {"image": "a1.png"})
    assert picture["type"] == "image" and picture["image"] == "a1.png"
    bar = upgrade_slide(old["bar-chart"])
    assert bar["type"] == "chart" and bar["kind"] == "bar" and bar["labels"] == ["Центр", "Север"]
    assert bar["series"] == [{"name": "млн", "values": [42, -17]}] and bar["bullets"] == ["в"]
    line = upgrade_slide(old["chart"])
    assert line["type"] == "chart" and line["kind"] == "line" and line["labels"] == ["Q1", "Q2"]
    assert upgrade_slide(old["title"]) == old["title"], "старые типы не трогаются"


def test_image_without_picture_and_bullets_becomes_section():
    # старый ImageSlide разрешал пустые bullets, новый TextSlide требует хотя бы один:
    # такой слайд в text сломал бы проверку, и перенос пропустил бы колоду целиком
    empty = {"id": "s000007", "type": "image", "title": "Пусто", "bullets": [],
             "image": None, "image_size": "medium", "caption": "", "notes": "н"}
    section = upgrade_slide(empty)
    assert section == {"id": "s000007", "type": "section", "title": "Пусто", "notes": "н"}
    Deck(slides=[section])


def test_migrate_keeps_deck_with_empty_image_slide(tmp_path):
    d = write_deck(tmp_path, "d0000000003", versions=1)
    raw = LEGACY | {"id": "d0000000003", "slides": LEGACY["slides"] + [
        {"id": "s000007", "type": "image", "title": "Пусто", "bullets": [],
         "image": None, "image_size": "medium"}]}
    (d / "deck.json").write_text(json.dumps(raw, ensure_ascii=False))
    assert ("d0000000003", 2) in migrate(tmp_path)
    assert json.loads((d / "deck.json").read_text())["slides"][-1]["type"] == "section"


def test_bar_chart_without_unit_names_the_series():
    bar = upgrade_slide({"id": "s1", "type": "bar-chart", "title": "x", "unit": "",
                         "data": [{"label": "A", "value": 1}], "bullets": []})
    assert bar["series"][0]["name"] == "Значение"


def test_migrate_rewrites_decks_versions_and_trash(tmp_path):
    write_deck(tmp_path, "d0000000001")
    trash = tmp_path / "trash" / "d0000000002-20260910T110407"
    (trash / "versions").mkdir(parents=True)
    (trash / "deck.json").write_text(json.dumps(LEGACY | {"id": "d0000000002"}, ensure_ascii=False))

    done = migrate(tmp_path)
    assert dict(done) == {"d0000000001": 3, "d0000000002": 1}
    deck = Deck.model_validate_json((tmp_path / "decks" / "d0000000001" / "deck.json").read_text())
    assert [s.type for s in deck.slides] == ["title", "text", "image", "chart", "chart", "final"]
    assert deck.version == 3, "перенос — не правка, версия не поднимается"
    assert [s.id for s in deck.slides] == [s["id"] for s in LEGACY["slides"]]
    snapshot = Deck.model_validate_json(
        (tmp_path / "decks" / "d0000000001" / "versions" / "000001.json").read_text())
    assert [s.type for s in snapshot.slides] == [s.type for s in deck.slides]
    assert Deck.model_validate_json((trash / "deck.json").read_text()).slides[1].type == "text"


def test_migrate_is_idempotent_and_check_writes_nothing(tmp_path):
    d = write_deck(tmp_path, "d0000000001")
    migrate(tmp_path)
    stamp = (d / "deck.json").stat().st_mtime_ns
    assert migrate(tmp_path) == [], "второй проход менять нечего"
    assert (d / "deck.json").stat().st_mtime_ns == stamp

    write_deck(tmp_path, "d0000000003")
    before = (tmp_path / "decks" / "d0000000003" / "deck.json").read_text()
    assert dict(migrate(tmp_path, check=True)) == {"d0000000003": 3}
    assert (tmp_path / "decks" / "d0000000003" / "deck.json").read_text() == before


def test_one_broken_deck_does_not_stop_the_run(tmp_path, capsys):
    """Перенос запускают один раз при остановленном сервисе: оператору нужна сводка,
    а не трассировка. upgrade_slide умеет бросить KeyError, AttributeError и TypeError."""
    write_deck(tmp_path, "d0000000001")
    for name, slides in (("d0000000002", [{"type": "bar-chart", "title": "без id",
                                           "data": [{"label": "A", "value": 1}]}]),
                         ("d0000000003", ["строка вместо слайда"])):
        d = tmp_path / "decks" / name
        d.mkdir(parents=True)
        (d / "deck.json").write_text(json.dumps(LEGACY | {"id": name, "slides": slides},
                                                ensure_ascii=False))
    broken = tmp_path / "decks" / "d0000000004"
    broken.mkdir(parents=True)
    (broken / "deck.json").write_text("[1, 2]")
    write_deck(tmp_path, "d0000000005")

    done = migrate(tmp_path)
    assert {deck_id for deck_id, _ in done} == {"d0000000001", "d0000000005"}
    err = capsys.readouterr().err
    assert all(f"d000000000{n}: пропущена" in err for n in (2, 3, 4)), err


def test_migrate_clears_the_preview_cache(tmp_path):
    """Спека §5: кэш template-previews/ очищается — иначе примонтированный канон
    без изменений файлов сохранит превью на шесть страниц вместо пятнадцати."""
    write_deck(tmp_path, "d0000000001")
    cached = tmp_path / "template-previews" / "default" / "build"
    cached.mkdir(parents=True)
    (cached / "slide-1.svg").write_text("<svg/>")
    migrate(tmp_path)
    assert not (tmp_path / "template-previews").exists()


def test_check_does_not_clear_the_preview_cache(tmp_path):
    write_deck(tmp_path, "d0000000001")
    cached = tmp_path / "template-previews" / "default" / "build"
    cached.mkdir(parents=True)
    (cached / "slide-1.svg").write_text("<svg/>")
    migrate(tmp_path, check=True)
    assert (cached / "slide-1.svg").exists(), "--check ничего не пишет и ничего не удаляет"


def test_broken_deck_is_left_alone(tmp_path):
    d = write_deck(tmp_path, "d0000000001")
    (d / "versions" / "000002.json").write_text("{не json")
    assert migrate(tmp_path) == []
    assert json.loads((d / "deck.json").read_text())["slides"][1]["type"] == "image", "колода целиком не тронута"


def test_migrate_drops_the_stale_build_of_rewritten_decks(tmp_path):
    """Старый build/ вызывает функции старого контракта (slide-bar-chart) и хранит
    старый PDF: после выкатки 2026-10-13 PDF колоды отвечал 500, превью были старыми."""
    live = write_deck(tmp_path, "d0000000004", versions=1)
    (live / "build").mkdir()
    (live / "build" / "deck.typ").write_text("#slide-bar-chart()")
    (live / "build" / "deck.pdf").write_bytes(b"%PDF old")
    trash = tmp_path / "trash" / "d0000000005-20260901T000000"
    trash.parent.mkdir()
    write_deck(tmp_path, "d0000000005", versions=1).rename(trash)
    (trash / "build").mkdir()
    migrate(tmp_path)
    assert not (live / "build").exists() and not (trash / "build").exists()


def test_check_keeps_the_build(tmp_path):
    d = write_deck(tmp_path, "d0000000006", versions=1)
    (d / "build").mkdir()
    migrate(tmp_path, check=True)
    assert (d / "build").is_dir()


def test_untouched_deck_keeps_its_build(tmp_path):
    """Колода уже на новых типах — её сборка верна, сносить нечего."""
    d = write_deck(tmp_path, "d0000000007", versions=1)
    migrate(tmp_path)
    (d / "build").mkdir()
    (d / "build" / "deck.typ").write_text("свежая")
    assert migrate(tmp_path) == [] and (d / "build" / "deck.typ").read_text() == "свежая"
