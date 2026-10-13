import asyncio
import base64

from tests.conftest import requires_typst
from typst_deck.model import Deck
from typst_deck.llm.client import Completion, ToolCall

pytestmark = requires_typst


async def test_agent_create_and_revise(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [
            {"type": "title", "title": "A"}, {"type": "final"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Собрано"})]),
    ]
    r = await client.post("/api/agent/create_deck", json={
        "brief": "презентацию",
        "files": [{"name": "d.txt", "content_base64": base64.b64encode("цифры".encode()).decode()}],
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "ready" and j["reply"] == "Собрано"
    assert j["outline"] == [{"n": 1, "type": "title", "title": "A"}, {"n": 2, "type": "final", "title": "Спасибо"}]
    assert j["pdf_url"].endswith(f"/api/decks/{j['deck_id']}/deck.pdf")
    assert j["pptx_url"] is None  # у шаблона default нет PowerPoint-мастера
    assert j["edit_url"].endswith(f"/d/{j['deck_id']}")
    assert "цифры" in fake_llm.calls[0][-1]["content"]

    d = (await client.get(f"/api/decks/{j['deck_id']}")).json()
    sid = d["deck"]["slides"][0]["id"]
    fake_llm._queue += [
        Completion("", [ToolCall("c3", "update_slide", {"slide_id": sid, "patch": {"title": "B"}})]),
        Completion("Заменил", []),
    ]
    r = await client.post("/api/agent/revise_deck", json={"deck_id": j["deck_id"], "request": "замени заголовок"})
    assert r.json()["outline"][0]["title"] == "B" and r.json()["reply"] == "Заменил"
    g = await client.get(f"/api/agent/decks/{j['deck_id']}")
    assert g.json()["outline"][0]["title"] == "B"
    assert (await client.get("/api/agent/decks/nope")).status_code == 404


async def test_agent_timeout_returns_generating(client, fake_llm):
    class Slow:
        async def complete(self, messages, tools):
            await asyncio.sleep(0.5)
            return Completion("ок", [])

    client.app.state.service.llm = Slow()
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "files": [], "wait_seconds": 0})
    assert r.status_code == 200 and r.json()["status"] == "generating"


async def test_agent_bad_file(client):
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "files": [{"name": "x.exe", "content_base64": "TVo="}]})
    assert r.status_code == 422
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "files": [{"name": "x.txt", "content_base64": "@@"}]})
    assert r.status_code == 422


async def test_agent_gets_pptx_url_when_the_template_has_a_master(pptx_client):
    from typst_deck.model import Deck

    deck = pptx_client.app.state.store.create(Deck(title="T", template="withpptx", slides=[{"type": "final"}]))
    j = (await pptx_client.get(f"/api/agent/decks/{deck.id}")).json()
    assert j["pptx_url"] == f"http://t/api/decks/{deck.id}/deck.pptx"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def test_render_deck_keeps_text_verbatim_without_the_llm(settings):
    """Готовая колода собирается как есть: без нейросети, текст — дословно."""
    import httpx

    from typst_deck.app import create_app

    app = create_app(settings, llm=None)
    deck = {"title": "Итоги квартала", "slides": [
        {"type": "title", "title": "Итоги  квартала — как есть", "subtitle": "Отдел данных"},
        {"type": "text", "title": "Главное", "bullets": ["Выручка +12 %", "Отток −3 п. п."]},
        {"type": "final"}]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/agent/render_deck", json={"deck": deck})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "ready" and j["pdf_url"].endswith(f"/api/decks/{j['deck_id']}/deck.pdf")
        assert [o["title"] for o in j["outline"]] == ["Итоги  квартала — как есть", "Главное", "Спасибо"]
        saved = app.state.store.load(j["deck_id"])
        assert saved.title == "Итоги квартала" and saved.template == "default"
        assert saved.slides[1].bullets == ["Выручка +12 %", "Отток −3 п. п."]
        assert (app.state.store.deck_dir(j["deck_id"]) / "build" / "slide-3.svg").exists()


async def test_render_deck_reports_errors_per_field_and_creates_nothing(tight_client):
    long = "Очень длинный заголовок заглавного слайда, который тесному шаблону не по силам"
    r = await tight_client.post("/api/agent/render_deck", json={"template": "tight", "deck": {"slides": [
        {"type": "title", "title": long},
        {"type": "text", "title": "x" * 121, "bullets": ["ок"]},
        {"type": "chart", "title": "Г", "kind": "line", "labels": ["Q1"], "series": [{"name": "р", "values": [1]}]},
        {"type": "nope"}]}})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation" and err["message"]
    fields = {f["path"]: f for f in err["fields"]}
    assert fields["slides.1.title"]["limit"] == 120 and fields["slides.1.title"]["actual"] == 121
    assert "slides.2" in fields and "две точки" in fields["slides.2"]["message"]
    assert "slides.3" in fields
    # пределы шаблона судятся, только когда модель колоды цела: иначе слайды не прочесть
    assert (await tight_client.get("/api/decks")).json() == []

    r = await tight_client.post("/api/agent/render_deck", json={"template": "tight", "deck": {"slides": [
        {"type": "title", "title": long}]}})
    assert r.status_code == 422
    [f] = r.json()["error"]["fields"]
    assert f["path"] == "slides.0.title" and f["limit"] == 60 and f["actual"] == len(long)
    assert "в шаблоне" in f["message"]
    assert (await tight_client.get("/api/decks")).json() == []


async def test_render_deck_takes_pictures_from_files(client):
    from tests.conftest import PNG_1PX as png

    r = await client.post("/api/agent/render_deck", json={
        "deck": {"slides": [{"type": "image", "title": "Схема", "image": "схема.png", "bullets": ["раз"]}]},
        "files": [{"name": "схема.png", "content_base64": _b64(png)}]})
    assert r.status_code == 200, r.text
    deck = client.app.state.store.load(r.json()["deck_id"])
    aid = deck.slides[0].image
    assert aid != "схема.png" and client.app.state.store.asset_path(deck.id, aid).read_bytes() == png

    r = await client.post("/api/agent/render_deck", json={
        "deck": {"slides": [{"type": "gallery", "title": "Г", "images": [
            {"image": "a.png"}, {"image": "нет.png"}]}]},
        "files": [{"name": "a.png", "content_base64": _b64(png)}]})
    assert r.status_code == 422
    [f] = r.json()["error"]["fields"]
    assert f["path"] == "slides.0.images.1.image" and "нет.png" in f["message"]


async def test_render_deck_rewrites_an_existing_deck(client):
    """С deck_id колода переписывается дословно новой версией — прежняя остаётся
    в истории; алиас шаблона разрешается, как у create_deck."""
    r = await client.post("/api/agent/render_deck", json={"deck": {"title": "Т", "slides": [{"type": "final"}]}})
    did = r.json()["deck_id"]
    r = await client.post("/api/agent/render_deck", json={"deck_id": did, "template": "dark", "deck": {
        "title": "Т2", "slides": [{"type": "section", "title": "Новое"}]}})
    assert r.status_code == 200, r.text
    assert r.json()["deck_id"] == did and r.json()["outline"] == [{"n": 1, "type": "section", "title": "Новое"}]
    deck = client.app.state.store.load(did)
    assert (deck.title, deck.template, deck.version) == ("Т2", "dark", 2)
    assert (await client.post("/api/agent/render_deck", json={"deck_id": "nope", "deck": {"slides": []}})).status_code == 404


async def test_render_deck_without_slides_is_a_field_error(client):
    r = await client.post("/api/agent/render_deck", json={"deck": {"slides": []}})
    assert r.status_code == 422
    assert r.json()["error"]["fields"][0]["path"] == "slides"
    assert (await client.get("/api/decks")).json() == []


async def test_render_deck_reports_ready_after_a_failed_generation(client, fake_llm):
    """Агент чинит колоду после провала модели: ответ render_deck — про эту сборку."""
    r = await client.post("/api/agent/create_deck", json={"brief": "x", "wait_seconds": 30})
    assert r.json()["status"] == "failed"  # очередь fake_llm пуста — генерация падает
    r = await client.post("/api/agent/render_deck", json={"deck_id": r.json()["deck_id"],
                                                          "deck": {"slides": [{"type": "final"}]}})
    assert r.status_code == 200 and r.json()["status"] == "ready" and r.json()["last_error"] is None


async def test_render_deck_refuses_a_deck_id_outside_decks(client):
    """id колоды — не путь: «../trash/…» вёл в корзину, мимо decks/."""
    store = client.app.state.store
    gone = store.delete(store.create(Deck(title="Т", slides=[{"type": "final"}])).id)
    r = await client.post("/api/agent/render_deck", json={"deck_id": f"../trash/{gone.name}",
                                                          "deck": {"slides": [{"type": "final"}]}})
    assert r.status_code == 404
    assert (await client.get(f"/api/agent/decks/..%2Ftrash%2F{gone.name}")).status_code == 404


async def test_failed_rewrite_leaves_no_new_pictures(client, monkeypatch):
    from tests.conftest import PNG_1PX as png
    from typst_deck.api.common import ApiError
    from typst_deck.service import DeckService

    r = await client.post("/api/agent/render_deck", json={"deck": {"slides": [{"type": "final"}]}})
    did = r.json()["deck_id"]

    async def boom(self, deck):
        raise ApiError(500, "render", "typst упал")

    monkeypatch.setattr(DeckService, "render", boom)
    r = await client.post("/api/agent/render_deck", json={"deck_id": did, "deck": {"slides": [
        {"type": "image", "title": "К", "image": "a.png"}]}, "files": [{"name": "a.png", "content_base64": _b64(png)}]})
    assert r.status_code == 500
    assert client.app.state.store.assets(did) == []
    assert [x.type for x in client.app.state.store.load(did).slides] == ["final"], "откат, как у manual"
