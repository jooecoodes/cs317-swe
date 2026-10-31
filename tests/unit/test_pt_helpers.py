"""Pure unit tests for pt_service helpers — no HTTP, no DB, no filesystem."""
from datetime import date

from pt_service.main import (
    safe_component, parse_tags, dump_tags,
    _join_naturally, _verb_phrase, _noun_phrase,
    summarize_actor_counts, summarize_action_totals,
    build_range_summary,
)


# ---------- safe_component (filename sanitization) ----------

def test_safe_component_keeps_alnum():
    assert safe_component("hello_world") == "hello_world"


def test_safe_component_replaces_spaces():
    assert safe_component("hello world") == "hello_world"


def test_safe_component_replaces_path_separators():
    assert "/" not in safe_component("a/b/c")
    assert "\\" not in safe_component("a\\b\\c")


def test_safe_component_truncates_to_80():
    assert len(safe_component("a" * 100)) == 80


def test_safe_component_falls_back():
    assert safe_component("") == "item"
    assert safe_component("   ") == "item"
    assert safe_component(None) == "item"


# ---------- tags ----------

def test_parse_tags_splits_on_comma():
    assert parse_tags("a,b,c") == ["a", "b", "c"]


def test_parse_tags_strips_whitespace():
    assert parse_tags(" a , b , c ") == ["a", "b", "c"]


def test_parse_tags_handles_empty():
    assert parse_tags("") == []
    assert parse_tags(None) == []


def test_dump_tags_deduplicates():
    assert dump_tags(["a", "b", "a"]) == "a,b"


def test_dump_tags_strips_commas_within_tags():
    assert dump_tags(["a,b"]) == "a b"


def test_dump_tags_returns_none_on_empty():
    assert dump_tags([]) is None
    assert dump_tags(None) is None


# ---------- sentence joining ----------

def test_join_naturally_one():
    assert _join_naturally(["X"]) == "X"


def test_join_naturally_two():
    assert _join_naturally(["X", "Y"]) == "X and Y"


def test_join_naturally_three():
    assert _join_naturally(["X", "Y", "Z"]) == "X, Y, and Z"


def test_join_naturally_empty():
    assert _join_naturally([]) == ""


# ---------- verb / noun phrase ----------

def test_verb_phrase_singular():
    assert _verb_phrase("upload", 1) == "uploaded 1 photo"


def test_verb_phrase_plural():
    assert _verb_phrase("upload", 3) == "uploaded 3 photos"


def test_noun_phrase_singular():
    assert _noun_phrase("upload", 1) == "1 upload"


def test_noun_phrase_plural():
    assert _noun_phrase("delete", 2) == "2 deletions"


# ---------- summarizers ----------

def test_summarize_actor_counts():
    assert summarize_actor_counts({"upload": 5, "edit": 2}) == (
        "uploaded 5 photos and edited 2 photos"
    )


def test_summarize_action_totals():
    assert summarize_action_totals({"upload": 25, "delete": 1}) == (
        "25 uploads and 1 deletion"
    )


# ---------- range summary ----------

def test_range_summary_empty_day():
    out = build_range_summary(date(2026, 1, 1), date(2026, 1, 1), 0, {}, {})
    assert "No activity on 2026-01-01" in out


def test_range_summary_empty_range():
    out = build_range_summary(date(2026, 1, 1), date(2026, 1, 10), 0, {}, {})
    assert "No activity between 2026-01-01 and 2026-01-10" in out


def test_range_summary_single_actor():
    out = build_range_summary(
        date(2026, 1, 1), date(2026, 1, 1), 5,
        {"upload": 5}, {"alice": 5},
    )
    assert "All by alice" in out


def test_range_summary_multi_actor():
    out = build_range_summary(
        date(2026, 1, 1), date(2026, 1, 10), 5,
        {"upload": 5}, {"alice": 3, "bob": 2},
    )
    assert "Most active: alice" in out
