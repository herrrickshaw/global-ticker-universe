"""Characterisation tests for universe_builder.build_universe / save_universe.

fixtures/universe_fallback_golden.json is build_universe() with an EMPTY data dir (static
fallback lists), captured from the pre-refactor code. Exchange suffixes come from the MARKETS
allowlist only; they are never inferred from ticker shape.
"""
import csv
import json
from pathlib import Path

import pytest

import universe_builder as ub

GOLD = json.loads((Path(__file__).parent / "fixtures" / "universe_fallback_golden.json").read_text())


@pytest.fixture
def empty_data(tmp_path, monkeypatch):
    monkeypatch.setattr(ub, "DATA", tmp_path)
    return tmp_path


def test_empty_data_dir_matches_golden(empty_data, capsys):
    assert json.loads(json.dumps(ub.build_universe())) == GOLD
    assert "  IN  :" in capsys.readouterr().out


def test_every_registered_source_is_unique_and_ordered():
    codes = [m.code for m in ub._UNIVERSE_SOURCES]
    assert len(codes) == len(set(codes))
    assert codes[:2] == ["IN", "US"]


def test_json_feed_dedups_and_prefers_file_over_fallback(empty_data):
    (empty_data / "jp_tickers_full.json").write_text(json.dumps(
        [{"yf_ticker": "7203.T"}, {"yf_ticker": "6758.T"}, {"yf_ticker": "7203.T"}]))
    assert ub.build_universe()["JP"]["yf_symbols"] == ["7203.T", "6758.T"]


def test_optional_market_omitted_without_file_and_present_with_it(empty_data):
    assert "SE" not in ub.build_universe()
    (empty_data / "se_tickers_full.json").write_text(json.dumps([{"yf_ticker": "VOLV-B.ST"}]))
    u = ub.build_universe()
    assert u["SE"]["yf_symbols"] == ["VOLV-B.ST"] and u["SE"]["count"] == 1


def test_china_combines_sse_and_szse_without_duplicates(empty_data):
    (empty_data / "cn_sse_tickers_full.json").write_text(json.dumps([{"yf_ticker": "600519.SS"}]))
    (empty_data / "cn_sz_tickers_full.json").write_text(json.dumps(
        [{"yf_ticker": "000001.SZ"}, {"yf_ticker": "600519.SS"}]))
    assert ub.build_universe()["CN"]["yf_symbols"] == ["600519.SS", "000001.SZ"]


def test_india_csv_uses_row_suffix_and_skips_blank_symbols(empty_data):
    with open(empty_data / "india_tickers_full.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Symbol", "Suffix"])
        w.writerows([["TCS", ".NS"], ["500325", ".BO"], ["", ".NS"], ["TCS", ".NS"]])
    assert ub.build_universe()["IN"]["yf_symbols"] == ["TCS.NS", "500325.BO"]


def test_us_symbols_sorted_from_file(empty_data):
    (empty_data / "us_tickers_full.json").write_text(json.dumps({"MSFT": {}, "AAPL": {}}))
    assert ub.build_universe()["US"]["yf_symbols"] == ["AAPL", "MSFT"]


def test_europe_file_merges_into_static_market(empty_data):
    (empty_data / "europe_tickers_full.json").write_text(json.dumps(
        [{"market_code": "CH", "yf_ticker": "ZZZZ.SW"}, {"market_code": "FI", "yf_ticker": "NOKIA.HE"}]))
    u = ub.build_universe()
    assert u["CH"]["yf_symbols"][-1] == "ZZZZ.SW"
    assert u["FI"]["yf_symbols"] == ["NOKIA.HE"] and u["FI"]["source"] == "europe_tickers_full.json"


def test_save_universe_writes_json_and_flat_csv(empty_data, capsys):
    uni = {"US": {"name": "United States", "exchange": "X", "yf_symbols": ["AAPL"], "count": 1}}
    ub.save_universe(uni)
    assert json.loads((empty_data / "global_universe.json").read_text()) == uni
    rows = list(csv.reader((empty_data / "global_universe_flat.csv").open()))
    assert rows == [["market_code", "market_name", "exchange", "yf_symbol"],
                    ["US", "United States", "X", "AAPL"]]
