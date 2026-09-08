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

    return Settings(data_dir=tmp_path / "data", template_dir=TEMPLATE_DIR, templates_dir=ROOT / "templates", public_base_url="http://t", llm_model="deepseek-chat")


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
