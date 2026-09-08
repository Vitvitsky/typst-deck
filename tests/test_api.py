import asyncio

import httpx

from tests.conftest import requires_typst
from typst_deck.llm.client import Completion, ToolCall


async def wait_job(client, job_id):
    for _ in range(300):
        j = (await client.get(f"/api/jobs/{job_id}")).json()
        if j["status"] in ("done", "failed"):
            return j
        await asyncio.sleep(0.02)
    raise AssertionError("задача не завершилась")


async def test_upload_and_errors(client):
    r = await client.post("/api/uploads", files={"file": ("brief.txt", b"hello", "text/plain")})
    assert r.status_code == 200 and r.json()["kind"] == "text" and r.json()["chars"] == 5
    r = await client.post("/api/uploads", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert (await client.get("/api/decks/nope")).status_code == 404
    r = await client.post("/api/decks", json={"brief": 5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"


async def test_create_without_llm_is_503(settings):
    from typst_deck.app import create_app

    app = create_app(settings, llm=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/decks", json={"brief": "x", "upload_ids": []})
        assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"
        assert (await c.get("/api/health")).json() == {"ok": True, "llm": False}


@requires_typst
async def test_full_flow(client, fake_llm, png_bytes):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "Итоги", "slides": [
            {"type": "title", "title": "Итоги", "subtitle": "Q3"},
            {"type": "image", "title": "Рост", "bullets": ["a", "b"]},
            {"type": "final"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово: 3 слайда"})]),
    ]
    up = (await client.post("/api/uploads", files={"file": ("brief.txt", "данные".encode(), "text/plain")})).json()
    r = await client.post("/api/decks", json={"brief": "сделай", "upload_ids": [up["upload_id"]]})
    assert r.status_code == 202
    deck_id, job_id = r.json()["deck_id"], r.json()["job_id"]
    assert (await client.get(f"/api/decks/{deck_id}")).json()["status"] in ("generating", "ready")
    job = await wait_job(client, job_id)
    assert job["status"] == "done", job
    d = (await client.get(f"/api/decks/{deck_id}")).json()
    assert d["status"] == "ready" and d["slide_count"] == 3 and d["edit_url"] == f"http://t/d/{deck_id}"
    assert "данные" in fake_llm.calls[0][-1]["content"]
    chat = (await client.get(f"/api/decks/{deck_id}/chat")).json()
    assert [m["role"] for m in chat] == ["user", "assistant"] and chat[1]["content"] == "Готово: 3 слайда"

    svg = await client.get(f"/api/decks/{deck_id}/slides/2.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert (await client.get(f"/api/decks/{deck_id}/slides/9.svg")).status_code == 404
    pdf = await client.get(f"/api/decks/{deck_id}/deck.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    pos = (await client.get(f"/api/decks/{deck_id}/positions")).json()
    assert any(p["field"] == "bullets" for p in pos)

    sid = d["deck"]["slides"][1]["id"]
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"title": "Новый"}})
    assert r.status_code == 200 and r.json()["deck"]["slides"][1]["title"] == "Новый"
    assert r.json()["version"] == 3
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"title": "x" * 500}})
    assert r.status_code == 422
    assert (await client.patch(f"/api/decks/{deck_id}/slides/s_nope", json={"patch": {}})).status_code == 404

    a = await client.post(f"/api/decks/{deck_id}/assets", files={"file": ("p.png", png_bytes, "image/png")})
    aid = a.json()["asset_id"]
    r = await client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"patch": {"image": aid}})
    assert r.json()["warnings"] == []

    r = await client.post(f"/api/decks/{deck_id}/slides",
                          json={"slide": {"type": "section", "title": "Р"}, "after": sid})
    assert r.json()["slide_count"] == 4 and r.json()["deck"]["slides"][2]["type"] == "section"
    new_sid = r.json()["deck"]["slides"][2]["id"]
    r = await client.post(f"/api/decks/{deck_id}/slides/{new_sid}/move", json={"to_index": 0})
    assert r.json()["deck"]["slides"][0]["id"] == new_sid
    r = await client.delete(f"/api/decks/{deck_id}/slides/{new_sid}")
    assert r.json()["slide_count"] == 3

    versions = (await client.get(f"/api/decks/{deck_id}/versions")).json()
    assert [v["version"] for v in versions][:2] == [1, 2]
    r = await client.post(f"/api/decks/{deck_id}/revert", json={"version": 2})
    assert r.json()["deck"]["slides"][1]["title"] == "Рост"
    assert (await client.post(f"/api/decks/{deck_id}/revert", json={"version": 99})).status_code == 404

    fake_llm._queue += [
        Completion("", [ToolCall("c3", "update_slide", {"slide_id": sid, "patch": {"title": "Через чат"}})]),
        Completion("Поменял", []),
    ]
    gate = asyncio.Event()

    class Gated:  # задерживает ответ LLM, чтобы задача была активна во время второго запроса
        async def complete(self, messages, tools):
            await gate.wait()
            return await fake_llm.complete(messages, tools)

    client.app.state.service.llm = Gated()
    r = await client.post(f"/api/decks/{deck_id}/messages", json={"text": "поменяй заголовок"})
    assert r.status_code == 202
    r2 = await client.post(f"/api/decks/{deck_id}/messages", json={"text": "ещё"})
    assert r2.status_code == 409
    gate.set()
    job = await wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    d = (await client.get(f"/api/decks/{deck_id}")).json()
    assert d["deck"]["slides"][1]["title"] == "Через чат"
    assert sid in fake_llm.calls[-1][0]["content"]
    users = [m["content"] for m in fake_llm.calls[-1] if m["role"] == "user"]
    assert any("данные" in u for u in users)  # файлы видны и при правке


@requires_typst
async def test_failed_generation_reports(client, fake_llm):
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    job = await wait_job(client, r.json()["job_id"])
    assert job["status"] == "failed" and "FakeLLM" in job["error"]
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["status"] == "failed" and d["last_error"]
    chat = (await client.get(f"/api/decks/{r.json()['deck_id']}/chat")).json()
    assert chat[-1]["role"] == "error"


async def test_list_decks(client):
    assert (await client.get("/api/decks")).json() == []
    from typst_deck.model import Deck
    store = client.app.state.store
    store.create(Deck(title="Первая", slides=[{"type": "final"}]))
    store.create(Deck(title="Вторая"))
    items = (await client.get("/api/decks")).json()
    assert [i["title"] for i in items] == ["Вторая", "Первая"]
    assert items[1]["slide_count"] == 1 and items[1]["status"] == "ready" and items[1]["has_build"] is False


@requires_typst
async def test_rename_materials_delete(client, fake_llm, png_bytes):
    from typst_deck.model import Deck
    store = client.app.state.store
    d = store.create(Deck(title="Старое", slides=[{"type": "final"}]))
    r = await client.patch(f"/api/decks/{d.id}", json={"title": "Новое"})
    assert r.status_code == 200 and r.json()["deck"]["title"] == "Новое" and r.json()["version"] == 2
    r = await client.post(f"/api/decks/{d.id}/uploads", files={"file": ("cat.png", png_bytes, "image/png")})
    assert r.json()["kind"] == "image" and r.json()["asset_id"].endswith(".png")
    r = await client.post(f"/api/decks/{d.id}/uploads", files={"file": ("notes.txt", "цифры".encode(), "text/plain")})
    assert r.json() == {"name": "notes.txt", "kind": "text", "chars": 5}
    assert store.list_uploads(d.id) == [("notes.txt", "цифры")]
    assert (await client.post(f"/api/decks/{d.id}/uploads", files={"file": ("x.exe", b"MZ", "x")})).status_code == 422
    assert (await client.delete(f"/api/decks/{d.id}")).status_code == 204
    assert (await client.get(f"/api/decks/{d.id}")).status_code == 404
    assert (await client.delete(f"/api/decks/{d.id}")).status_code == 404


@requires_typst
async def test_job_phase_and_changes_in_chat(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    job = await wait_job(client, r.json()["job_id"])
    assert job["status"] == "done" and job["phase"] == "render" and job["created_at"]
    chat = (await client.get(f"/api/decks/{r.json()['deck_id']}/chat")).json()
    assert chat[-1]["changes"][0]["kind"] == "rebuilt" and chat[-1]["changes"][0]["count"] == 1
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["job"] is None


@requires_typst
async def test_templates_history_and_template_choice(client, fake_llm):
    ts = (await client.get("/api/templates")).json()
    assert [t["id"] for t in ts] == ["default", "dark"] and ts[1]["name"] == "Тёмный"
    svg = await client.get("/api/templates/dark/preview/1.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    assert (await client.get("/api/templates/dark/preview/9.svg")).status_code == 404
    assert (await client.get("/api/templates/nope/preview/1.svg")).status_code == 422

    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "ok"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "тёмная", "upload_ids": [], "template": "dark"})
    assert r.status_code == 202
    await wait_job(client, r.json()["job_id"])
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["deck"]["template"] == "dark" and d["template"]["name"] == "Тёмный" and d["has_build"]
    assert (await client.post("/api/decks", json={"brief": "x", "upload_ids": [], "template": "nope"})).status_code == 422

    h = (await client.get("/api/history")).json()
    assert h[0]["text"] == "тёмная" and h[0]["deck_id"] == r.json()["deck_id"] and h[0]["deck_title"] == "T"
