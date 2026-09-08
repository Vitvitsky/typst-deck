import json

import httpx
import pytest
import respx

from typst_deck.llm.client import Completion, FakeLLM, LLMError, OpenAICompatLLM, ToolCall

TOOLS = [{"type": "function", "function": {"name": "finish", "parameters": {
    "type": "object", "properties": {"summary": {"type": "string"}}}}}]
URL = "https://llm.test/v1/chat/completions"


async def test_fake_llm_records_and_replays():
    llm = FakeLLM([Completion("a", []), Completion("b", [])])
    assert (await llm.complete([{"role": "user", "content": "x"}], [])).text == "a"
    assert (await llm.complete([], [])).text == "b"
    assert llm.calls[0][0]["content"] == "x"
    with pytest.raises(LLMError):
        await llm.complete([], [])


@respx.mock
async def test_tools_mode_parses_tool_calls():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "finish", "arguments": "{\"summary\": \"ok\"}"}}]}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m")
    c = await llm.complete([{"role": "user", "content": "hi"}], TOOLS)
    assert c.text == "" and c.tool_calls == [ToolCall("c1", "finish", {"summary": "ok"})]
    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "m" and body["tools"] == TOOLS and body["messages"][0]["content"] == "hi"
    assert route.calls[0].request.headers["authorization"] == "Bearer k"


@respx.mock
async def test_json_mode_rewrites_messages_and_parses():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": "Вот: {\"tool\": \"finish\", \"args\": {\"summary\": \"ok\"}}"}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m", tool_mode="json")
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c0", "type": "function", "function": {"name": "finish", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c0", "content": "done"},
    ]
    c = await llm.complete(msgs, TOOLS)
    assert c.tool_calls[0].name == "finish" and c.tool_calls[0].arguments == {"summary": "ok"}
    body = json.loads(route.calls[0].request.content)
    assert "tools" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "system", "assistant", "user"]
    assert "finish" in body["messages"][1]["content"]
    assert body["messages"][3]["content"].startswith("Результат finish:")


@respx.mock
async def test_json_mode_reply():
    respx.post(URL).mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": "{\"reply\": \"готово\"}"}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m", tool_mode="json")
    c = await llm.complete([{"role": "user", "content": "x"}], TOOLS)
    assert c.text == "готово" and c.tool_calls == []


@respx.mock
async def test_http_error():
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m")
    with pytest.raises(LLMError):
        await llm.complete([{"role": "user", "content": "x"}], TOOLS)


@respx.mock
async def test_length_cutoff_is_error():
    respx.post(URL).mock(return_value=httpx.Response(200, json={
        "choices": [{"finish_reason": "length", "message": {"content": "", "reasoning_content": "думаю…"}}]}))
    llm = OpenAICompatLLM("https://llm.test/v1", "k", "m", max_tokens=10)
    with pytest.raises(LLMError, match="max_tokens=10"):
        await llm.complete([{"role": "user", "content": "x"}], TOOLS)
