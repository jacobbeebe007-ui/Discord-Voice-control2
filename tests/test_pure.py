"""Unit tests for stateless helpers (no Discord runtime)."""
from halo_bot.pure import (
    calculate_mmr,
    canonical_name,
    halo_rank,
    normalise,
    parse_names,
)


def test_canonical_name_strips_parenthetical():
    assert canonical_name("Foo (bar)") == "Foo"
    assert canonical_name("  Baz  ") == "Baz"


def test_parse_names_comma_and_newline():
    assert parse_names("a, b, c") == ["a", "b", "c"]
    assert parse_names("x\ny,z") == ["x", "y", "z"]
    assert parse_names("  ,  \n") == []


def test_normalise_spread_and_tie():
    assert normalise([0, 10, 20]) == [0.0, 50.0, 100.0]
    assert normalise([5, 5, 5]) == [50.0, 50.0, 50.0]


def test_halo_rank_thresholds():
    assert halo_rank(0)[0] == "Recruit"
    assert halo_rank(95.5)[0] == "Inheritor"
    assert halo_rank(50)[0] == "Brigadier"
    assert halo_rank(50.5)[0] == "General"


def test_calculate_mmr_weighted():
    players = [
        {"kd": 2.0, "points": 100, "obj_time": 60, "assists": 10, "captures": 5},
        {"kd": 1.0, "points": 50, "obj_time": 30, "assists": 5, "captures": 2},
    ]
    out = calculate_mmr([dict(p) for p in players])
    assert len(out) == 2
    assert out[0]["mmr"] > out[1]["mmr"]
