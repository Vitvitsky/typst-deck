"""Тесты чистых функций интерфейса (static/editors.js) — node --test, если Node есть."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_editors_js():
    # Node 22 не принимает каталог аргументом --test: передаются сами файлы
    files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    assert files, "нет тестов в tests/js"
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
