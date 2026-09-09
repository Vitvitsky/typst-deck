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
        h = (await c.get("/api/health")).json()
        assert h["ok"] is True and h["llm"] is False and h["model"] is None


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
async def test_change_template(client):
    from typst_deck.model import Deck
    store = client.app.state.store
    d = store.create(Deck(title="Старое", slides=[{"type": "final"}]))
    r = await client.post(f"/api/decks/{d.id}/template", json={"template": "dark"})
    assert r.status_code == 200 and r.json()["deck"]["template"] == "dark"
    assert r.json()["template"]["name"] == "Тёмный" and r.json()["version"] == 2 and r.json()["has_build"]
    assert (await client.post(f"/api/decks/{d.id}/template", json={"template": "nope"})).status_code == 422
    assert (await client.get(f"/api/decks/{d.id}")).json()["deck"]["template"] == "dark"


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
    ids = [t["id"] for t in ts]
    # только шаблоны, которые есть в git: lmru-hr на свежем клоне отсутствует, и его
    # отсутствие ловят test_compile.py и сборка образа, а не тест про выбор шаблона
    assert ids[0] == "default" and "dark" in ids and ts[ids.index("dark")]["name"] == "Тёмный"
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


def _render_boom(monkeypatch):
    from typst_deck.api.common import ApiError
    from typst_deck.service import DeckService

    def boom(self, deck):
        raise ApiError(500, "render", "шаблон не собрался")

    monkeypatch.setattr(DeckService, "render", boom)


@requires_typst
async def test_failed_render_in_generate_reverts_deck(client, fake_llm, monkeypatch):
    """Провал рендера не оставляет сохранённой колоду, которая не собирается."""
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "Первый"}]})]),
        Completion("готово", []),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    assert (await wait_job(client, r.json()["job_id"]))["status"] == "done"
    good = (await client.get(f"/api/decks/{deck_id}")).json()["deck"]

    _render_boom(monkeypatch)
    fake_llm._queue += [
        Completion("", [ToolCall("c2", "set_deck", {"title": "T2", "slides": [{"type": "title", "title": "Второй"}]})]),
        Completion("готово", []),
    ]
    r2 = await client.post(f"/api/decks/{deck_id}/messages", json={"text": "поменяй"})
    assert (await wait_job(client, r2.json()["job_id"]))["status"] == "failed"
    after = (await client.get(f"/api/decks/{deck_id}")).json()["deck"]
    assert [s["title"] for s in after["slides"]] == [s["title"] for s in good["slides"]]


@requires_typst
async def test_failed_template_change_keeps_working_template(client, fake_llm, monkeypatch):
    """Смена шаблона с провалом рендера не должна запирать колоду на несобираемом оформлении."""
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("готово", []),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    assert (await wait_job(client, r.json()["job_id"]))["status"] == "done"

    _render_boom(monkeypatch)
    assert (await client.post(f"/api/decks/{deck_id}/template", json={"template": "dark"})).status_code == 500
    assert (await client.get(f"/api/decks/{deck_id}")).json()["deck"]["template"] == "default"


@requires_typst
async def test_generate_records_tokens_in_chat(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})],
                   tokens_in=1000, tokens_out=200, tokens_cached=800),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})],
                   tokens_in=1500, tokens_out=90, tokens_cached=1400),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    assert (await wait_job(client, r.json()["job_id"]))["status"] == "done"
    reply = (await client.get(f"/api/decks/{r.json()['deck_id']}/chat")).json()[-1]
    assert reply["role"] == "assistant"
    assert reply["tokens_in"] == 2500 and reply["tokens_out"] == 290
    assert reply["tokens_cached"] == 2200 and reply["iterations"] == 2
    assert reply["llm_ms"] >= 0


@requires_typst
async def test_generate_logs_stages_with_deck_and_job(client, fake_llm, caplog):
    caplog.set_level("INFO", logger="typst_deck.service")
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id, job_id = r.json()["deck_id"], r.json()["job_id"]
    assert (await wait_job(client, job_id))["status"] == "done"
    events = {rec.msg: rec.fields for rec in caplog.records if hasattr(rec, "fields")}
    assert {"job.start", "stage.reading", "job.done"} <= set(events)
    assert events["job.start"]["deck"] == deck_id and events["job.start"]["job"] == job_id
    assert events["stage.reading"]["files"] == 0
    assert events["job.done"]["v"] == 2 and events["job.done"]["slides"] == 1
    assert events["job.done"]["tok_in"] == 0 and events["job.done"]["ms"] >= 0


@requires_typst
async def test_failed_generation_logs_job_failed(client, fake_llm, caplog):
    caplog.set_level("INFO", logger="typst_deck.service")
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    assert (await wait_job(client, r.json()["job_id"]))["status"] == "failed"
    failed = [rec for rec in caplog.records if rec.msg == "job.failed"]
    assert len(failed) == 1
    assert failed[0].fields["deck"] == r.json()["deck_id"]
    assert "LLMError" in failed[0].fields["err"]


@requires_typst
async def test_manual_edit_logs_op(client, fake_llm, caplog):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])
    caplog.set_level("INFO", logger="typst_deck.service")
    assert (await client.patch(f"/api/decks/{deck_id}", json={"title": "Новое"})).status_code == 200
    done = [x for x in caplog.records if x.msg == "manual.done"]
    assert len(done) == 1
    assert done[0].fields["deck"] == deck_id and done[0].fields["v"] == 3 and done[0].fields["ms"] >= 0


async def test_health_reports_zero_tokens_before_any_call(client):
    h = (await client.get("/api/health")).json()
    assert h["tokens"] == {"in": 0, "out": 0, "cached": 0, "requests": 0}
    assert h["since"]


@requires_typst
async def test_health_accumulates_tokens_across_generations(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})],
                   tokens_in=1000, tokens_out=200, tokens_cached=800),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})],
                   tokens_in=1500, tokens_out=90, tokens_cached=1400),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    await wait_job(client, r.json()["job_id"])
    h = (await client.get("/api/health")).json()
    assert h["tokens"] == {"in": 2500, "out": 290, "cached": 2200, "requests": 2}


async def test_request_timing_is_logged(client, caplog):
    caplog.set_level("INFO", logger="typst_deck.app")
    await client.get("/api/decks")
    http = [r for r in caplog.records if r.msg == "http"]
    assert len(http) == 1
    assert http[0].fields["method"] == "GET"
    assert http[0].fields["path"] == "/api/decks"
    assert http[0].fields["status"] == 200
    assert http[0].fields["ms"] >= 0


async def test_health_requests_are_not_logged(client, caplog):
    caplog.set_level("INFO", logger="typst_deck.app")
    await client.get("/api/health")
    assert [r for r in caplog.records if r.msg == "http"] == []


async def test_create_app_installs_log_handler(settings):
    import logging as _logging

    from typst_deck.app import create_app
    from typst_deck.logs import HANDLER_MARK

    for h in list(_logging.getLogger().handlers):
        if getattr(h, HANDLER_MARK, False):
            _logging.getLogger().removeHandler(h)
    create_app(settings, llm=None)
    assert any(getattr(h, HANDLER_MARK, False) for h in _logging.getLogger().handlers)


@requires_typst
async def test_render_does_not_block_event_loop(client, fake_llm, monkeypatch):
    """Пока идёт компиляция typst, сервер обязан отвечать на другие запросы."""
    import time

    from typst_deck import service as service_mod

    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])

    real_compile = service_mod.compile_deck

    def slow_compile(*a, **kw):
        time.sleep(0.4)  # блокирующий вызов, как настоящий subprocess.run
        return real_compile(*a, **kw)

    monkeypatch.setattr(service_mod, "compile_deck", slow_compile)

    # мерим от старта правки: если цикл занят компиляцией, ответить раньше неё нельзя
    started = time.perf_counter()
    edit = asyncio.create_task(client.patch(f"/api/decks/{deck_id}", json={"title": "Новое"}))
    await asyncio.sleep(0.05)  # даём правке дойти до компиляции
    probe = await client.get("/api/decks")
    probe_s = time.perf_counter() - started

    assert probe.status_code == 200
    assert probe_s < 0.3, f"параллельный запрос ждал рендера {probe_s:.2f} с — цикл заблокирован"
    assert (await edit).status_code == 200


@requires_typst
async def test_template_preview_does_not_block_event_loop(client, monkeypatch):
    """Первое превью шаблона компилирует образец — тоже в потоке, не в цикле."""
    import time

    from typst_deck import service as service_mod

    real_compile = service_mod.compile_deck

    def slow_compile(*a, **kw):
        time.sleep(0.4)
        return real_compile(*a, **kw)

    monkeypatch.setattr(service_mod, "compile_deck", slow_compile)

    started = time.perf_counter()
    preview = asyncio.create_task(client.get("/api/templates/dark/preview/1.svg"))
    await asyncio.sleep(0.05)
    probe = await client.get("/api/decks")
    probe_s = time.perf_counter() - started

    assert probe.status_code == 200
    assert probe_s < 0.3, f"параллельный запрос ждал превью {probe_s:.2f} с — цикл заблокирован"
    assert (await preview).status_code == 200


@requires_typst
async def test_concurrent_first_previews_of_same_template(client):
    """Раньше компиляции сериализовал заблокированный цикл. Теперь они в потоках,
    и два первых превью одного шаблона не должны драться за build.tmp."""
    rs = await asyncio.gather(*(client.get("/api/templates/dark/preview/1.svg") for _ in range(4)))
    assert [r.status_code for r in rs] == [200, 200, 200, 200]
    assert all(r.content.startswith(b"<svg") or b"<svg" in r.content[:200] for r in rs)


@requires_typst
async def test_deck_response_carries_page_size(client, fake_llm):
    """Размер страницы приходит вместе с колодой: фронту незачем качать slide-1.svg ради viewBox."""
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    await wait_job(client, r.json()["job_id"])
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["page"] == {"w": 453.543307087, "h": 255.118110236}


async def test_deck_response_page_size_without_build(client, fake_llm):
    from typst_deck.render import DEFAULT_PAGE

    fake_llm._queue += [Completion("нет правок", [])]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    await wait_job(client, r.json()["job_id"])
    d = (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()
    assert d["has_build"] is False and d["page"] == DEFAULT_PAGE


@requires_typst
async def test_slide_svg_is_cacheable_by_version(client, fake_llm):
    """URL слайда версионирован ?v=, поэтому содержимое под ним неизменно:
    no-store заставлял браузер качать все слайды заново после каждой правки."""
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])
    v = (await client.get(f"/api/decks/{deck_id}")).json()["version"]

    svg = await client.get(f"/api/decks/{deck_id}/slides/1.svg?v={v}")
    cc = svg.headers["cache-control"]
    assert "no-store" not in cc
    assert "immutable" in cc and "max-age=" in cc
    assert "private" in cc, "колоды за Basic Auth — общим прокси их кэшировать нельзя"
    assert svg.headers["etag"], "ETag нужен, чтобы работал условный запрос"


@requires_typst
async def test_slide_svg_answers_304_on_revalidation(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])

    first = await client.get(f"/api/decks/{deck_id}/slides/1.svg?v=2")
    again = await client.get(f"/api/decks/{deck_id}/slides/1.svg?v=2",
                             headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


@requires_typst
async def test_deck_response_carries_per_slide_versions(client, fake_llm):
    """Версия на слайд: правка одного слайда не должна менять URL остальных."""
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [
            {"type": "title", "title": "Первый"},
            {"type": "section", "title": "Второй"},
            {"type": "final"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])

    d = (await client.get(f"/api/decks/{deck_id}")).json()
    before = d["pages"]
    assert len(before) == 3 and len(set(before)) == 3

    sid = d["deck"]["slides"][1]["id"]
    after = (await client.patch(f"/api/decks/{deck_id}/slides/{sid}",
                                json={"patch": {"title": "Изменённый"}})).json()["pages"]
    assert after[1] != before[1]
    assert [after[0], after[2]] == [before[0], before[2]]


async def test_deck_response_pages_empty_without_build(client, fake_llm):
    fake_llm._queue += [Completion("нет правок", [])]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    await wait_job(client, r.json()["job_id"])
    assert (await client.get(f"/api/decks/{r.json()['deck_id']}")).json()["pages"] == []


@requires_typst
async def test_pdf_is_built_on_demand_and_reused(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])

    build = client.app.state.service.store.deck_dir(deck_id) / "build"
    assert not (build / "deck.pdf").exists(), "после сборки колоды PDF ещё не нужен"
    assert (await client.get(f"/api/decks/{deck_id}")).json()["has_build"] is True

    first = await client.get(f"/api/decks/{deck_id}/deck.pdf")
    assert first.status_code == 200 and first.content[:5] == b"%PDF-"
    stamp = (build / "deck.pdf").stat().st_mtime_ns

    second = await client.get(f"/api/decks/{deck_id}/deck.pdf")
    assert second.status_code == 200
    assert (build / "deck.pdf").stat().st_mtime_ns == stamp, "готовый PDF не должен пересобираться"


@requires_typst
async def test_pdf_rebuilt_after_edit(client, fake_llm):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])
    await client.get(f"/api/decks/{deck_id}/deck.pdf")

    await client.patch(f"/api/decks/{deck_id}", json={"title": "Другое имя"})
    build = client.app.state.service.store.deck_dir(deck_id) / "build"
    assert not (build / "deck.pdf").exists(), "правка обязана обнулить готовый PDF"
    assert (await client.get(f"/api/decks/{deck_id}/deck.pdf")).content[:5] == b"%PDF-"


@requires_typst
async def test_pdf_build_is_logged(client, fake_llm, caplog):
    fake_llm._queue += [
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Готово"})]),
    ]
    r = await client.post("/api/decks", json={"brief": "x", "upload_ids": []})
    deck_id = r.json()["deck_id"]
    await wait_job(client, r.json()["job_id"])
    caplog.set_level("INFO", logger="typst_deck.render")
    await client.get(f"/api/decks/{deck_id}/deck.pdf")
    done = [x for x in caplog.records if x.msg == "pdf.done"]
    assert len(done) == 1 and done[0].fields["ms"] >= 0 and done[0].fields["kb"] > 0
