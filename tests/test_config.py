import os

from typst_deck.config import get_settings


def test_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("TYPST_DECK_") or k.startswith("DEEPSEEK_"):
            monkeypatch.delenv(k)
    s = get_settings()
    assert s.typst_bin == "typst"
    assert s.llm_tool_mode == "tools"
    assert s.llm_api_key == ""


def test_deepseek_synonyms(monkeypatch):
    monkeypatch.delenv("TYPST_DECK_LLM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    s = get_settings()
    assert s.llm_api_key == "sk-x"
    assert s.llm_model == "deepseek-chat"
    assert s.llm_api_base == "https://api.deepseek.com"


def test_prefix_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("TYPST_DECK_LLM_API_KEY", "sk-y")
    assert get_settings().llm_api_key == "sk-y"


def test_templates_dirs_is_path_like(monkeypatch):
    monkeypatch.setenv("TYPST_DECK_TEMPLATES_DIR", "/app/templates:/private")
    assert [str(p) for p in get_settings().templates_dirs] == ["/app/templates", "/private"]
    monkeypatch.delenv("TYPST_DECK_TEMPLATES_DIR")
    assert [str(p) for p in get_settings().templates_dirs] == ["templates"]
