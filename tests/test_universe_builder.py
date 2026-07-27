"""Tests for universe_builder.py — the pure dedup helper and the market registry.

build_universe() itself reads many external ticker files, so we test the pure,
deterministic pieces: order-preserving dedup and the MARKETS registry shape.
"""
import universe_builder as ub


def test_dedup_preserves_first_seen_order():
    assert ub._dedup(["a", "b", "a", "c", "b", "a"]) == ["a", "b", "c"]


def test_dedup_empty_list():
    assert ub._dedup([]) == []


def test_dedup_no_duplicates_unchanged():
    assert ub._dedup(["x", "y", "z"]) == ["x", "y", "z"]


def test_dedup_keeps_all_when_unique_symbols():
    syms = ["AAPL", "MSFT", "RELIANCE.NS", "7203.T"]
    assert ub._dedup(syms) == syms


def test_markets_registry_is_wellformed():
    assert len(ub.MARKETS) >= 15
    for code, m in ub.MARKETS.items():
        assert isinstance(code, str) and code.isupper() and len(code) == 2
        assert "name" in m and "exchange" in m
        assert "suffix" in m  # None for IN/US, "" for US, ".XX" otherwise


def test_markets_covers_core_regions():
    assert {"US", "IN", "JP", "UK", "DE", "CN"} <= set(ub.MARKETS)


def test_markets_known_suffixes():
    assert ub.MARKETS["JP"]["suffix"] == ".T"
    assert ub.MARKETS["UK"]["suffix"] == ".L"
    assert ub.MARKETS["DE"]["suffix"] == ".DE"
    assert ub.MARKETS["IN"]["suffix"] is None   # NSE/BSE stored bare
