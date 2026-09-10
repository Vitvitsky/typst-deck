"""Общие фикстуры тестов."""
import base64
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "template"
HAS_TYPST = shutil.which("typst") is not None
requires_typst = pytest.mark.skipif(not HAS_TYPST, reason="typst не установлен")

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def deck_dir(tmp_path: Path) -> Path:
    d = tmp_path / "deck"
    (d / "assets").mkdir(parents=True)
    return d


@pytest.fixture
def png_bytes() -> bytes:
    return PNG_1PX


@pytest.fixture
def settings(tmp_path):
    from typst_deck.config import Settings

    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, templates_dir=str(ROOT / "templates"), public_base_url="http://t", llm_model="deepseek-chat")


@pytest.fixture
def fake_llm():
    from typst_deck.llm.client import FakeLLM

    return FakeLLM([])


@pytest.fixture
async def client(settings, fake_llm):
    import httpx

    from typst_deck.app import create_app

    app = create_app(settings, llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c


@pytest.fixture
def tight_settings(tmp_path):
    """Клиент с шаблоном, у которого объявлена ёмкость слотов.

    Шаблон — копия default: важна не вёрстка, а объявление в template.json.
    """
    import json
    import shutil as sh

    from typst_deck.config import Settings

    root = tmp_path / "templates"
    tight = root / "tight"
    tight.mkdir(parents=True)
    sh.copy(TEMPLATE_DIR / "deck.typ", tight / "deck.typ")
    (tight / "template.json").write_text(json.dumps({
        "name": "Тесный",
        "slots": {"title": {"title": {"max": 60}, "subtitle": {"lines": 2}},
                  "image": {"bullets": {"count": 3}}},
    }, ensure_ascii=False))
    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, templates_dir=str(root),
                    public_base_url="http://t", llm_model="deepseek-chat")


@pytest.fixture
async def tight_client(tight_settings, fake_llm):
    import httpx

    from typst_deck.app import create_app

    app = create_app(tight_settings, llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c
