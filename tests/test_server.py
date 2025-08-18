import json

import pytest

from orchestrator.server import parse_queries_from_prompt, simple_queries, chunk_text


def test_parse_queries_from_prompt_json(monkeypatch):
    monkeypatch.setattr('orchestrator.server.N_QUERIES', 2, raising=False)
    prompt = json.dumps({'queries': ['q1', 'q2', 'q3'], 'claim': 'some claim'})
    queries, claim = parse_queries_from_prompt(prompt)
    assert queries == ['q1', 'q2']
    assert claim == 'some claim'


def test_parse_queries_from_prompt_structured(monkeypatch):
    monkeypatch.setattr('orchestrator.server.N_QUERIES', 5, raising=False)
    prompt = (
        "QUERIES:\n"
        "1. first query\n"
        "- second query\n"
        "CLAIM:\n"
        "This is the claim"
    )
    queries, claim = parse_queries_from_prompt(prompt)
    assert queries == ['first query', 'second query']
    assert claim == 'This is the claim'


def test_simple_queries_generation():
    prompt = 'CLAIM TO EVALUATE: "The Moon is made of cheese and is delicious"'
    result = simple_queries(prompt, 3)
    assert result == ['moon made cheese delicious'] * 3


def test_chunk_text_short_text():
    assert chunk_text('short text') == []


def test_chunk_text_overlap_logic():
    text = 'x' * 2500
    chunks = chunk_text(text, size=1000, overlap=100)
    assert len(chunks) == 3
    assert chunks[0][1:] == (0, 1000)
    assert chunks[1][1:] == (900, 1900)
    assert chunks[2][1:] == (1800, 2500)
    assert [len(seg) for seg, _, _ in chunks] == [1000, 1000, 700]
