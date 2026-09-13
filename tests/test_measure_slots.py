import json
import subprocess
import sys

from tests.conftest import ROOT, make_template, requires_typst

SCRIPT = ROOT / "scripts" / "measure_slots.py"


def _measure(tdir):
    return subprocess.run([sys.executable, str(SCRIPT), str(tdir)], capture_output=True, text=True)


@requires_typst
def test_measures_slots_from_the_template_measure_file(tmp_path):
    d = make_template(tmp_path, "m", meta={"name": "М", "measure": "measure.json"})
    (d / "measure.json").write_text(json.dumps({
        "import": "deck.typ",
        "sample": "Итоги квартала по направлению ",
        "list": "#set list(spacing: 0.35em)",
        "probes": [
            {"slide": "title", "field": "title", "width": "138mm", "height": "24mm",
             "size": "28pt", "weight": "bold", "font": "\"DejaVu Sans\""},
            {"slide": "image", "field": "bullets", "width": "80mm", "height": "40mm", "item": "12mm",
             "size": "11pt", "weight": "regular", "font": "\"DejaVu Sans\""},
        ],
    }, ensure_ascii=False))
    r = _measure(d)
    assert r.returncode == 0, r.stderr
    slots = json.loads(r.stdout)["slots"]
    assert 5 <= slots["title"]["title"]["max"] <= 400 and slots["title"]["title"]["lines"] >= 1
    assert slots["image"]["bullets"]["count"] >= 1 and slots["image"]["bullets"]["max"] >= 5
    assert not list(d.glob("_measure*.typ"))  # временные файлы убраны


@requires_typst
def test_probe_with_dotted_field_reaches_slots_and_survives_clamp(tmp_path):
    """Проба вложенного поля (columns.blocks.text) печатается под ключом с точкой
    как есть и не отбрасывается clamp'ом — это тот же путь, что понимает slots.py."""
    d = make_template(tmp_path, "dotted", meta={"name": "Т", "measure": "measure.json"})
    (d / "measure.json").write_text(json.dumps({
        "import": "deck.typ",
        "probes": [
            {"slide": "columns", "field": "blocks.text", "width": "80mm", "height": "24mm",
             "size": "11pt", "weight": "regular", "font": "\"DejaVu Sans\""},
        ],
    }, ensure_ascii=False))
    r = _measure(d)
    assert r.returncode == 0, r.stderr
    slots = json.loads(r.stdout)["slots"]
    assert "blocks.text" in slots["columns"]
    assert slots["columns"]["blocks.text"]["max"] >= 5

    from typst_deck.slots import clamp

    declared = clamp({"columns": slots["columns"]}, "dotted")
    assert declared["columns"]["blocks.text"] == slots["columns"]["blocks.text"]


def test_template_without_measure_is_refused(tmp_path):
    d = make_template(tmp_path, "nomeasure")
    r = _measure(d)
    assert r.returncode != 0 and "measure" in r.stderr
