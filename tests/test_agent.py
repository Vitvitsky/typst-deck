import json

from typst_deck.llm.agent import Outcome, build_system_prompt, run_agent
from typst_deck.llm.client import Completion, FakeLLM, ToolCall
from typst_deck.llm.tools import ToolExecutor, tool_specs
from typst_deck.model import Deck
from typst_deck.slots import clamp


def test_tool_specs_shape():
    specs = tool_specs()
    names = [s["function"]["name"] for s in specs]
    assert names == ["set_deck", "update_slide", "add_slide", "remove_slide", "move_slide", "set_template", "finish"]
    assert all(s["type"] == "function" and "parameters" in s["function"] for s in specs)
    assert "bar-chart" in json.dumps(specs)


def test_tool_specs_set_template_enum():
    names = [s["function"]["name"] for s in tool_specs(["default", "dark", "lmru-hr"])]
    assert names == ["set_deck", "update_slide", "add_slide", "remove_slide", "move_slide", "set_template", "finish"]
    st = next(s for s in tool_specs(["default", "dark", "lmru-hr"]) if s["function"]["name"] == "set_template")
    assert st["function"]["parameters"]["properties"]["template"]["enum"] == ["default", "dark", "lmru-hr"]


def test_executor_set_template():
    ex = ToolExecutor(Deck(), template_ids=["default", "dark", "lmru-hr"])
    r = ex.call("set_template", {"template": "dark"})
    assert r.startswith("OK") and ex.changed and ex.deck.template == "dark"
    assert ex.ops == ["set_template dark"]
    assert ex.changes == [{"kind": "template", "template_id": "dark"}]
    r = ex.call("set_template", {"template": "nope"})
    assert r.startswith("ERROR") and "nope" in r and "dark" in r
    assert ex.deck.template == "dark" and len(ex.ops) == 1


def test_executor_set_template_unknown_ok_without_whitelist():
    ex = ToolExecutor(Deck())
    assert ex.call("set_template", {"template": "lmru-hr"}).startswith("OK")
    assert ex.deck.template == "lmru-hr"
    assert ex.call("set_template", {"template": "Bad/Name"}).startswith("ERROR")


def test_executor_set_and_update():
    ex = ToolExecutor(Deck())
    r = ex.call("set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}, {"type": "final"}]})
    assert r.startswith("OK") and ex.changed and len(ex.deck.slides) == 2
    sid = ex.deck.slides[0].id
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "B"}}).startswith("OK")
    assert ex.deck.slides[0].title == "B"
    assert ex.call("update_slide", {"slide_id": "s_nope", "patch": {}}).startswith("ERROR")
    assert ex.call("update_slide", {"slide_id": sid, "patch": {"title": "x" * 500}}).startswith("ERROR")
    assert ex.call("nope", {}).startswith("ERROR")
    assert ex.call("update_slide", {"bogus": 1}).startswith("ERROR")
    assert ex.ops[:2] == ["set_deck", f"update_slide {sid}"]


def test_executor_add_remove_move_finish():
    ex = ToolExecutor(Deck(slides=[{"type": "final"}]))
    fid = ex.deck.slides[0].id
    ex.call("add_slide", {"slide": {"type": "section", "title": "S"}, "after": None})
    ex.call("move_slide", {"slide_id": ex.deck.slides[1].id, "to_index": 0})
    assert ex.deck.slides[0].type == "section"
    ex.call("remove_slide", {"slide_id": fid})
    assert len(ex.deck.slides) == 1
    assert ex.call("finish", {"summary": "готово"}) == "OK"
    assert ex.finished and ex.summary == "готово"


def test_system_prompt_mentions_schema_deck_assets():
    d = Deck(title="T", slides=[{"type": "final"}])
    p = build_system_prompt(d, ["a1.png"])
    assert "bar-chart" in p and '"T"' in p and "a1.png" in p and d.slides[0].id in p


def test_system_prompt_lists_templates():
    templates = [
        {"id": "default", "name": "Корпоративный", "description": ""},
        {"id": "dark", "name": "Тёмный", "description": ""},
    ]
    d = Deck(title="T", slides=[{"type": "final"}])
    p = build_system_prompt(d, [], templates=templates)
    assert "default" in p and "Корпоративный" in p and "dark" in p and "Тёмный" in p
    assert '"template":"default"' in p


async def test_run_agent_set_template_flow():
    d = Deck(title="T", slides=[{"type": "final"}])
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "set_template", {"template": "dark"})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Сменил шаблон"})]),
    ])
    out = await run_agent(llm, d, "сделай тёмной", files=[], history=[], assets=[],
                          templates=[{"id": "default", "name": "Корпоративный"},
                                     {"id": "dark", "name": "Тёмный"}])
    assert out.changed and out.reply == "Сменил шаблон"
    assert out.deck.template == "dark" and out.ops == ["set_template dark"]
    assert out.changes == [{"kind": "template", "template_id": "dark"}]
    sysmsg = llm.calls[0][0]["content"]
    assert "Тёмный" in sysmsg and '"template":"default"' in sysmsg


async def test_run_agent_create_flow():
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}]})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "Собрал 1 слайд"})]),
    ])
    out = await run_agent(llm, Deck(), "сделай", files=[("brief.txt", "текст задания")], history=[], assets=[])
    assert isinstance(out, Outcome) and out.changed and out.reply == "Собрал 1 слайд"
    assert out.deck.title == "T" and out.ops == ["set_deck"]
    first = llm.calls[0]
    assert first[0]["role"] == "system"
    assert "brief.txt" in first[-1]["content"] and "текст задания" in first[-1]["content"]
    second = llm.calls[1]
    assert second[-2]["role"] == "assistant" and second[-1]["role"] == "tool"
    assert second[-1]["content"].startswith("OK")


async def test_run_agent_error_feedback_then_fix():
    d = Deck(slides=[{"type": "title", "title": "A"}])
    sid = d.slides[0].id
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "update_slide", {"slide_id": sid, "patch": {"title": "x" * 500}})]),
        Completion("", [ToolCall("c2", "update_slide", {"slide_id": sid, "patch": {"title": "Короткий"}})]),
        Completion("Поправил заголовок", []),
    ])
    out = await run_agent(llm, d, "поправь", files=[], history=[], assets=[])
    assert out.deck.slides[0].title == "Короткий" and out.reply == "Поправил заголовок"
    assert llm.calls[1][-1]["content"].startswith("ERROR")


async def test_run_agent_iteration_limit():
    d = Deck(slides=[{"type": "title", "title": "A"}])
    sid = d.slides[0].id
    llm = FakeLLM([
        Completion("", [ToolCall(f"c{i}", "update_slide", {"slide_id": sid, "patch": {"title": f"T{i}"}})])
        for i in range(3)
    ])
    out = await run_agent(llm, d, "x", files=[], history=[], assets=[], max_iter=2)
    assert out.deck.slides[0].title == "T1" and "лимит" in out.reply.lower()


async def test_run_agent_uses_history():
    llm = FakeLLM([Completion("ок", [])])
    history = [{"role": "user", "content": "раньше"}, {"role": "assistant", "content": "ответ"}]
    await run_agent(llm, Deck(), "ещё", files=[], history=history, assets=[])
    assert [m["role"] for m in llm.calls[0]] == ["system", "user", "assistant", "user"]


async def test_empty_completion_gets_explanation():
    llm = FakeLLM([Completion("", [])])
    out = await run_agent(llm, Deck(), "x", files=[], history=[], assets=[])
    assert not out.changed and "не вернула" in out.reply


def test_executor_records_changes():
    ex = ToolExecutor(Deck())
    ex.call("set_deck", {"title": "T", "slides": [{"type": "title", "title": "A"}, {"type": "final"}]})
    sid = ex.deck.slides[0].id
    ex.call("update_slide", {"slide_id": sid, "patch": {"title": "B", "subtitle": "s"}})
    ex.call("remove_slide", {"slide_id": ex.deck.slides[1].id})
    kinds = [c["kind"] for c in ex.changes]
    assert kinds == ["rebuilt", "updated", "removed"]
    assert ex.changes[1] == {"kind": "updated", "slide_id": sid, "type": "title", "title": "B", "fields": ["subtitle", "title"]}
    assert ex.changes[2]["title"] == "Спасибо"


async def test_run_agent_sums_tokens_across_iterations():
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "update_slide", {"n": 1, "patch": {"title": "A"}})],
                   tokens_in=1000, tokens_out=200, tokens_cached=800),
        Completion("", [ToolCall("c2", "finish", {"summary": "готово"})],
                   tokens_in=1500, tokens_out=90, tokens_cached=1400),
    ])
    deck = Deck(slides=[{"type": "title", "title": "T"}])
    out = await run_agent(llm, deck, "поправь", [], [], [])
    assert out.tokens_in == 2500
    assert out.tokens_out == 290
    assert out.tokens_cached == 2200
    assert out.iterations == 2


async def test_run_agent_counts_single_reply_iteration():
    out = await run_agent(FakeLLM([Completion("ответ", [], tokens_in=40, tokens_out=7)]),
                          Deck(), "привет", [], [], [])
    assert (out.tokens_in, out.tokens_out, out.tokens_cached) == (40, 7, 0)
    assert out.iterations == 1


async def test_run_agent_reports_llm_time():
    out = await run_agent(FakeLLM([Completion("ответ", [])]), Deck(), "привет", [], [], [])
    assert out.llm_ms >= 0


def test_outcome_defaults_to_zero_tokens():
    o = Outcome(reply="x", changed=False, ops=[], deck=Deck())
    assert (o.tokens_in, o.tokens_out, o.tokens_cached, o.iterations, o.llm_ms) == (0, 0, 0, 0, 0)


async def test_run_agent_logs_each_llm_call(caplog):
    caplog.set_level("INFO", logger="typst_deck.llm.agent")
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "finish", {"summary": "готово"})],
                   tokens_in=1000, tokens_out=200, tokens_cached=800),
    ])
    await run_agent(llm, Deck(), "поправь", [], [], [])
    done = [r for r in caplog.records if r.msg == "llm.done"]
    assert len(done) == 1
    assert done[0].fields["tok_in"] == 1000
    assert done[0].fields["tok_out"] == 200
    assert done[0].fields["cached"] == 800
    assert done[0].fields["iter"] == 1


def test_system_prompt_uses_template_limits():
    d = Deck(title="T", slides=[{"type": "title", "title": "A"}])
    declared = clamp({"title": {"title": {"max": 60, "lines": 1}}})
    p = build_system_prompt(d, [], slots=declared)
    assert '"maxLength":60' in p.replace(" ", "") and "без переводов строки" in p
    assert '"maxLength":120' in p.replace(" ", "")  # у остальных полей предел прежний


def test_system_prompt_without_slots_shows_global_limits():
    d = Deck(title="T", slides=[{"type": "title", "title": "A"}])
    p = build_system_prompt(d, [])
    assert '"maxLength":120' in p.replace(" ", "") and '"maxLength":60' not in p.replace(" ", "")


async def test_run_agent_passes_limits_to_prompt_and_executor():
    d = Deck(title="T", slides=[{"type": "title", "title": "Итоги"}])
    sid = d.slides[0].id
    llm = FakeLLM([
        Completion("", [ToolCall("c1", "update_slide", {"slide_id": sid, "patch": {"title": "Э" * 80}})]),
        Completion("", [ToolCall("c2", "finish", {"summary": "готово"})]),
    ])
    await run_agent(llm, d, "правь", [], [], [], slots=clamp({"title": {"title": {"max": 60}}}),
                    template_name="Тесный")
    assert '"maxLength":60' in llm.calls[0][0]["content"].replace(" ", "")


async def test_run_agent_passes_render_errors_as_valid_role():
    """Ошибка рендера должна дойти до модели, но роли "error" в API нет —
    её надо переложить в допустимую, иначе провайдер отвергнет запрос."""
    llm = FakeLLM([Completion("понял", [])])
    history = [
        {"role": "user", "content": "добавь отступы"},
        {"role": "error", "content": "CompileError: слайд 1 «Титул» не помещается на страницу"},
    ]
    await run_agent(llm, Deck(), "ещё раз", [], history, [])
    sent = llm.calls[0]
    assert all(m["role"] in ("system", "user", "assistant", "tool") for m in sent), \
        [m["role"] for m in sent]
    assert any("не помещается на страницу" in (m.get("content") or "") for m in sent), \
        "модель обязана увидеть, почему прошлая правка не собралась"
