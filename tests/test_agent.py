import json

from typst_deck.llm.agent import Outcome, build_system_prompt, run_agent
from typst_deck.llm.client import Completion, FakeLLM, ToolCall
from typst_deck.llm.tools import ToolExecutor, tool_specs
from typst_deck.model import Deck


def test_tool_specs_shape():
    specs = tool_specs()
    names = [s["function"]["name"] for s in specs]
    assert names == ["set_deck", "update_slide", "add_slide", "remove_slide", "move_slide", "finish"]
    assert all(s["type"] == "function" and "parameters" in s["function"] for s in specs)
    assert "bar-chart" in json.dumps(specs)


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
