"""Tests for global_tickers.py — the lazy universe loader + ticker accessors.

Points the module's _DATA at a temp fixture universe and resets its module-level
cache before each test, so nothing touches the real data/global_universe.json.
"""
import json

import pytest

import global_tickers as gt


@pytest.fixture
def loaded(tmp_path, monkeypatch):
    universe = {
        "US": {"name": "United States", "exchange": "NYSE/NASDAQ",
               "yf_symbols": ["AAPL", "MSFT"], "count": 2},
        "IN": {"name": "India", "exchange": "NSE/BSE",
               "yf_symbols": ["RELIANCE.NS"], "count": 1},
    }
    f = tmp_path / "global_universe.json"
    f.write_text(json.dumps(universe))
    monkeypatch.setattr(gt, "_DATA", f)
    monkeypatch.setattr(gt, "_UNIVERSE", None)   # clear lazy cache
    return gt


def test_load_reads_json(loaded):
    assert set(loaded._load()) == {"US", "IN"}


def test_tickers_for_single_market(loaded):
    assert loaded.tickers_for("US") == ["AAPL", "MSFT"]


def test_tickers_for_is_case_insensitive(loaded):
    assert loaded.tickers_for("us") == ["AAPL", "MSFT"]


def test_tickers_for_multi_market_concatenates(loaded):
    assert loaded.tickers_for("US", "IN") == ["AAPL", "MSFT", "RELIANCE.NS"]


def test_tickers_for_unknown_market_raises(loaded):
    with pytest.raises(ValueError, match="Unknown market"):
        loaded.tickers_for("ZZ")


def test_all_tickers_flattens_every_market(loaded):
    assert sorted(loaded.all_tickers()) == ["AAPL", "MSFT", "RELIANCE.NS"]


def test_market_codes_lists_keys(loaded):
    assert set(loaded.market_codes()) == {"US", "IN"}


def test_load_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(gt, "_DATA", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(gt, "_UNIVERSE", None)
    assert gt._load() == {}


def test_load_is_cached(loaded):
    first = loaded._load()
    loaded._DATA.unlink()          # remove the file after first load
    assert loaded._load() is first  # cached object returned, not re-read
