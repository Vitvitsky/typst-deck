import pytest

from typst_deck.model import Deck
from typst_deck.store import DeckNotFound, DeckStore


@pytest.fixture
def store(tmp_path):
    return DeckStore(tmp_path / "data")


def test_create_load(store):
    d = store.create(Deck(title="A", slides=[{"type": "final"}]))
    assert d.version == 1
    assert store.load(d.id).title == "A"
    assert store.list_versions(d.id) == [1]
    with pytest.raises(DeckNotFound):
        store.load("nope")


def test_save_bumps_version_and_snapshots(store):
    d = store.create(Deck(slides=[{"type": "final"}]))
    d.title = "B"
    d = store.save(d)
    assert d.version == 2 and store.list_versions(d.id) == [1, 2]
    assert store.load_version(d.id, 1).title == "Презентация"
    assert d.updated_at > d.created_at


def test_revert_creates_new_version(store):
    d = store.create(Deck(title="v1", slides=[{"type": "final"}]))
    d.title = "v2"
    store.save(d)
    r = store.revert(d.id, 1)
    assert r.title == "v1" and r.version == 3
    assert store.load(d.id).title == "v1"


def test_assets(store, png_bytes):
    d = store.create(Deck())
    aid = store.add_asset(d.id, "Фото.PNG", png_bytes)
    assert aid.startswith("a") and aid.endswith(".png") and len(aid) == 11
    assert store.asset_path(d.id, aid).read_bytes() == png_bytes
    assert store.assets(d.id) == [aid]
    with pytest.raises(ValueError):
        store.add_asset(d.id, "x.exe", b"MZ")


def test_uploads_and_chat(store):
    d = store.create(Deck())
    store.add_upload(d.id, "brief.txt", b"hello", "hello")
    assert store.list_uploads(d.id) == [("brief.txt", "hello")]
    store.append_chat(d.id, {"role": "user", "content": "привет"})
    store.append_chat(d.id, {"role": "assistant", "content": "готово"})
    assert [m["role"] for m in store.read_chat(d.id)] == ["user", "assistant"]


def test_staged_uploads(store):
    uid = store.stage_upload("a.txt", b"x", "x")
    assert store.take_upload(uid) == ("a.txt", b"x", "x")
    with pytest.raises(KeyError):
        store.take_upload("nope")


def test_atomic_write_leaves_no_tmp(store):
    d = store.create(Deck())
    files = {p.name for p in store.deck_dir(d.id).iterdir()}
    assert "deck.json" in files and not any(n.endswith(".tmp") for n in files)


def test_lock_is_per_deck(store):
    assert store.lock("a") is store.lock("a") and store.lock("a") is not store.lock("b")


def test_list_decks_newest_first(store):
    a = store.create(Deck(title="A"))
    b = store.create(Deck(title="B"))
    (store.deck_dir("broken")).mkdir(parents=True)
    (store.deck_dir("broken") / "deck.json").write_text("{not json")
    assert [d.title for d in store.list_decks()] == ["B", "A"]
    a.title = "A2"
    store.save(a)
    assert [d.title for d in store.list_decks()] == ["A2", "B"]


def test_delete_moves_to_trash(store):
    d = store.create(Deck(title="X"))
    dst = store.delete(d.id)
    assert not store.exists(d.id) and dst.parent.name == "trash" and (dst / "deck.json").exists()
    with pytest.raises(DeckNotFound):
        store.delete(d.id)
