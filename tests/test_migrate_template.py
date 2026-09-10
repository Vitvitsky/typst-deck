import pytest

from typst_deck.migrate_template import main, migrate
from typst_deck.model import Deck
from typst_deck.store import DeckStore


def test_migrate_moves_only_decks_on_the_old_id(tmp_path):
    store = DeckStore(tmp_path)
    a = store.create(Deck(title="A", template="lmru-hr"))
    b = store.create(Deck(title="B", template="dark"))
    before = store.load(a.id)
    assert migrate(store, "lmru-hr", "lemana-tech") == [a.id]
    after = store.load(a.id)
    assert after.template == "lemana-tech"
    assert after.version == before.version and after.updated_at == before.updated_at  # это не правка
    assert store.load_version(a.id, before.version).template == "lmru-hr"  # снимки не тронуты
    assert store.load(b.id).template == "dark"


def test_migrate_twice_changes_nothing_the_second_time(tmp_path):
    store = DeckStore(tmp_path)
    store.create(Deck(template="lmru-hr"))
    migrate(store, "lmru-hr", "lemana-tech")
    assert migrate(store, "lmru-hr", "lemana-tech") == []


def test_migrate_refuses_an_invalid_new_id(tmp_path):
    with pytest.raises(ValueError):
        migrate(DeckStore(tmp_path), "lmru-hr", "Bad/Id")


def test_main_reads_data_dir_from_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TYPST_DECK_DATA_DIR", str(tmp_path))
    DeckStore(tmp_path).create(Deck(template="lmru-hr"))
    assert main(["lmru-hr", "lemana-tech"]) == 0
    assert "колод 1" in capsys.readouterr().out
    assert main(["only-one"]) == 2
