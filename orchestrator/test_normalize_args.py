import pytest
from orchestrator.server import normalize_args, MAX_QUERIES


def test_direct_queries():
    args = {"queries": ["ant", "bee"], "claim": "c"}
    out = normalize_args(args)
    assert out["queries"] == ["ant", "bee"]
    assert out["claim"] == "c"


def test_nested_json_string():
    args = {"prompt": '{"queries":["a","b"],"claim":"x"}'}
    out = normalize_args(args)
    assert out == {"queries": ["a", "b"], "claim": "x"}


def test_code_fenced_json():
    args = {"prompt": "```json\n{\"queries\":[\"a\",\"b\"]}\n```"}
    out = normalize_args(args)
    assert out["queries"] == ["a", "b"]


def test_bullet_list():
    text = "QUERIES:\n- a\n- b\nCLAIM: c"
    out = normalize_args({"prompt": text})
    assert out == {"queries": ["a", "b"], "claim": "c"}


def test_newline_list():
    text = "alpha\nbeta"
    out = normalize_args({"prompt": text})
    assert out["queries"] == ["alpha", "beta"]


def test_single_query_alias():
    out = normalize_args({"query": "a"})
    assert out["queries"] == ["a"]


def test_query_cap():
    many = {"queries": [f"q{i}" for i in range(MAX_QUERIES + 5)]}
    out = normalize_args(many)
    assert len(out["queries"]) == MAX_QUERIES


def test_empty_error():
    with pytest.raises(ValueError):
        normalize_args({})
