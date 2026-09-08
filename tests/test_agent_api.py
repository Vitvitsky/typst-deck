import asyncio
import base64

from tests.conftest import requires_typst
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
