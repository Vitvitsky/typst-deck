"""Ориентация столбцов: правило шаблона charts.columns (charts.py), одно для PDF и PPTX."""
import pytest

from typst_deck.charts import horizontal, parse_rule

RULE = {"full": [(4, 18), (12, 8)], "bullets": [(4, 10)]}


def test_no_rule_keeps_columns_vertical():
    assert parse_rule({}) is None
    assert horizontal(["Стройматериалы"] * 24, "full", None) is False


def test_columns_stay_vertical_while_some_pair_fits():
    assert horizontal(["Q1", "Q2", "Q3", "Q4"], "full", RULE) is False          # 2 знака, 4 ≤ 18
    assert horizontal(["Январь"] * 8, "full", RULE) is False                     # 6 ≤ 12, 8 ≤ 8
    assert horizontal(["Январь"] * 9, "full", RULE) is True                      # 9 > 8, 6 > 4
    assert horizontal(["Стройматериалы"] * 2, "full", RULE) is True              # 14 > 12


def test_layout_without_pairs_is_vertical_and_layouts_differ():
    labels = ["Q1"] * 12
    assert horizontal(labels, "full", RULE) is False
    assert horizontal(labels, "bullets", RULE) is True    # 12 > 10
    assert horizontal(labels, "dual", RULE) is False      # раскладку шаблон не обмерял


def test_length_counts_graphemes_not_combining_marks():
    # «й» из «и» + комбинирующей краткой — один знак, как у Typst (clusters)
    assert horizontal(["й" * 4], "full", {"full": [(4, 1)]}) is False


def test_rule_is_parsed_and_broken_rule_is_an_error():
    assert parse_rule({"charts": {"columns": {"full": [[4, 18]]}}}) == {"full": [(4, 18)]}
    for bad in ({"charts": []}, {"charts": {"rows": {}}}, {"charts": {"columns": {"wide": []}}},
                {"charts": {"columns": {"full": [[4]]}}}, {"charts": {"columns": {"full": [[0, 3]]}}},
                {"charts": {"columns": {"full": [[True, 3]]}}}, {"charts": {"columns": {"full": [["4", 3]]}}}):
        with pytest.raises(ValueError):
            parse_rule(bad)
