"""global_tickers.market_summary and edge cases (kept separate from test_global_tickers.py)."""
import json

import pytest

import global_tickers as gt


@pytest.fixture
def loaded(tmp_path, monkeypatch):
    universe = {
        "US": {"name": "United States", "exchange": "NYSE/NASDAQ", "yf_symbols": ["AAPL", "MSFT"], "count": 2},
        "IN": {"name": "India", "exchange": "NSE/BSE", "yf_symbols": ["RELIANCE.NS"], "count": 1},
    }
    f = tmp_path / "global_universe.json"
    f.write_text(json.dumps(universe))
    monkeypatch.setattr(gt, "_DATA", f)
    monkeypatch.setattr(gt, "_UNIVERSE", None)
    return gt


def test_market_summary_prints_table_and_total(loaded, capsys):
    loaded.market_summary()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["Code", "Market", "Exchange", "Tickers"]
    assert lines[1] == "─" * 78
    assert lines[2].startswith("US    United States") and lines[2].endswith("       2")
    assert lines[3].startswith("IN    India") and lines[3].endswith("       1")
    assert lines[-1].startswith("TOTAL 2 markets") and lines[-1].endswith("       3")


def test_market_summary_empty_universe(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gt, "_DATA", tmp_path / "missing.json")
    monkeypatch.setattr(gt, "_UNIVERSE", None)
    gt.market_summary()
    assert capsys.readouterr().out.splitlines()[-1].startswith("TOTAL 0 markets")


def test_tickers_for_no_codes_is_empty(loaded):
    assert loaded.tickers_for() == []
