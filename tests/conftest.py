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
