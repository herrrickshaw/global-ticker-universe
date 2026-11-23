"""global_scanner: scoring, universe assembly, batch fetch, scan loop, Excel export and CLI (offline)."""
import json
import sys
import types

import numpy as np
import pandas as pd
import pytest

import global_scanner as gs


# ---- helpers ---------------------------------------------------------------------------

def test_pct_scales_fractions_only():
    assert gs._pct(None) is None
    assert gs._pct(0.18) == 18.0
    assert gs._pct(-0.5) == -50.0
    assert gs._pct(1.999) == 199.9              # |v| < 2 is read as a fraction
    assert gs._pct(2) == 2                      # |v| >= 2 is already a percentage
    assert gs._pct(-2) == -2
    assert gs._pct(18.456) == 18.46
    assert gs._pct(0) == 0


def test_score_breakpoints():
    bp = [(0, 0), (10, 4), (20, 8), (1e9, 1)]
    assert gs._score(-1, bp) == 0
    assert gs._score(0, bp) == 4                # strictly less-than: 0 is not < 0
    assert gs._score(9.99, bp) == 4
    assert gs._score(10, bp) == 8
    assert gs._score(20, bp) == 1
    assert gs._score(1e12, bp) == 1             # beyond every threshold -> last score
    assert gs._score(None, bp) == 1
    assert gs._score(float("nan"), bp) == 1


# ---- Pegu ------------------------------------------------------------------------------

PERFECT = {"pe_ratio": 12, "peg_ratio": 0.4, "pb_ratio": 0.8, "roe": 22, "operating_margins": 18,
           "debt_to_equity": 10, "earnings_growth": 22, "revenue_growth": 12, "last_price": 100,
           "eps_forward": 10, "current_ratio": 2.5, "dividend_yield": 3.5, "beta": 0.9}


def test_pegu_hand_computed_perfect_row():
    # valuation 8+6+6=20; quality min(22+10+12, 30)=30; growth min(20+7+6, 25)=25; safety min(12+5+3, 15)=15
    assert gs.pegu_score(PERFECT) == (90.0, "A+")


def test_pegu_component_caps():
    # every component is capped at its maximum (30/30/25/15)
    best = dict(PERFECT, roe=40, operating_margins=40, earnings_growth=40, revenue_growth=40, current_ratio=5)
    assert gs.pegu_score(best)[0] <= 100.0


GRADE_ROWS = [
    # total, grade, row  (rows found by search; the totals are asserted so a scoring change is caught)
    (24, "F", {"pe_ratio": None, "peg_ratio": -1, "pb_ratio": 7, "roe": 3, "operating_margins": 12, "debt_to_equity": 150,
               "earnings_growth": -5, "revenue_growth": -5, "eps_forward": 50, "last_price": None, "current_ratio": 0.8,
               "dividend_yield": None, "beta": 2.0}),
    (25, "D", {"pe_ratio": 40, "peg_ratio": None, "pb_ratio": -1, "roe": 8, "operating_margins": 8, "debt_to_equity": 150,
               "earnings_growth": 3, "revenue_growth": 3, "eps_forward": None, "last_price": None, "current_ratio": 0.3,
               "dividend_yield": 8, "beta": 2.0}),
    (39, "D", {"pe_ratio": 12, "peg_ratio": 1.8, "pb_ratio": 7, "roe": -3, "operating_margins": 8, "debt_to_equity": 30,
               "earnings_growth": 3, "revenue_growth": -5, "eps_forward": 10, "last_price": None, "current_ratio": 0.3,
               "dividend_yield": 8, "beta": 1.1}),
    (40, "C", {"pe_ratio": -1, "peg_ratio": None, "pb_ratio": 12, "roe": -3, "operating_margins": 27, "debt_to_equity": 150,
               "earnings_growth": 3, "revenue_growth": 8, "eps_forward": 50, "last_price": None, "current_ratio": 4,
               "dividend_yield": 8, "beta": 0.3}),
    (49, "C", {"pe_ratio": -1, "peg_ratio": 1.8, "pb_ratio": None, "roe": 22, "operating_margins": -3, "debt_to_equity": 150,
               "earnings_growth": 3, "revenue_growth": 3, "eps_forward": 5, "last_price": None, "current_ratio": 1.7,
               "dividend_yield": 3.5, "beta": 2.0}),
    (50, "B", {"pe_ratio": 5, "peg_ratio": 2.5, "pb_ratio": None, "roe": -3, "operating_margins": 35, "debt_to_equity": 60,
               "earnings_growth": -5, "revenue_growth": 8, "eps_forward": 5, "last_price": None, "current_ratio": 2.5,
               "dividend_yield": 3.5, "beta": 1.1}),
    (59, "B", {"pe_ratio": 60, "peg_ratio": 1.8, "pb_ratio": 12, "roe": 35, "operating_margins": 35, "debt_to_equity": None,
               "earnings_growth": 3, "revenue_growth": 12, "eps_forward": 50, "last_price": 100, "current_ratio": 0.8,
               "dividend_yield": 3.5, "beta": 1.4}),
    (60, "B+", {"pe_ratio": -1, "peg_ratio": -1, "pb_ratio": 1.5, "roe": 3, "operating_margins": 35, "debt_to_equity": 150,
                "earnings_growth": None, "revenue_growth": 18, "eps_forward": 10, "last_price": 100, "current_ratio": 0.3,
                "dividend_yield": 0.5, "beta": 1.1}),
    (69, "B+", {"pe_ratio": 18, "peg_ratio": 1.8, "pb_ratio": 2.5, "roe": 18, "operating_margins": 18, "debt_to_equity": 100,
                "earnings_growth": -5, "revenue_growth": 12, "eps_forward": 0, "last_price": 100, "current_ratio": 0.3,
                "dividend_yield": 3.5, "beta": 1.1}),
    (70, "A", {"pe_ratio": 40, "peg_ratio": 0.8, "pb_ratio": 7, "roe": 18, "operating_margins": 35, "debt_to_equity": 60,
               "earnings_growth": 8, "revenue_growth": None, "eps_forward": None, "last_price": 100, "current_ratio": 0.3,
               "dividend_yield": 3.5, "beta": 2.0}),
    (79, "A", {"pe_ratio": 30, "peg_ratio": 1.2, "pb_ratio": 12, "roe": 35, "operating_margins": 27, "debt_to_equity": None,
               "earnings_growth": 22, "revenue_growth": 18, "eps_forward": 0, "last_price": 100, "current_ratio": 1.2,
               "dividend_yield": None, "beta": 2.0}),
    (80, "A+", {"pe_ratio": 5, "peg_ratio": 0.3, "pb_ratio": None, "roe": 22, "operating_margins": 22, "debt_to_equity": -5,
                "earnings_growth": None, "revenue_growth": -5, "eps_forward": 0, "last_price": 100, "current_ratio": 4,
                "dividend_yield": 2.5, "beta": 1.4}),
]


@pytest.mark.parametrize("total,grade,row", GRADE_ROWS, ids=[f"{t}-{g}" for t, g, _ in GRADE_ROWS])
def test_pegu_grade_boundaries(total, grade, row):
    assert gs.pegu_score(row) == (float(total), grade)


def test_pegu_negative_debt_to_equity_scores_max_safety_and_beta_uses_abs():
    base = dict(PERFECT, debt_to_equity=-5)
    assert gs.pegu_score(base) == gs.pegu_score(dict(PERFECT, debt_to_equity=0.0 + 1))
    assert gs.pegu_score(dict(PERFECT, beta=-0.9)) == gs.pegu_score(dict(PERFECT, beta=0.9))


def test_pegu_forward_pe_needs_positive_forward_eps_and_price():
    with_fwd = gs.pegu_score(dict(PERFECT, earnings_growth=0.5, revenue_growth=-1))[0]
    no_fwd = gs.pegu_score(dict(PERFECT, earnings_growth=0.5, revenue_growth=-1, eps_forward=-3))[0]
    assert with_fwd != no_fwd


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="_score(None, ...) returns the LAST breakpoint's score, which is the maximum for ROE/margin/"
                          "growth/current-ratio, so a row with no data at all scores 70 = grade 'A' (daily_scan_excel "
                          "treats missing values as neutral instead)")
def test_pegu_row_without_any_data_is_not_grade_a():
    total, grade = gs.pegu_score({})
    assert grade not in ("A", "A+"), (total, grade)


# ---- Sarvas ----------------------------------------------------------------------------

FACTORS = {
    "rsi": ({"rsi_14": 50}, 7), "macd": ({"macd": 0.1}, 5), "vr": ({"volume_ratio": 2.0}, 5),
    "h52": ({"week52_high": 100.0}, 7), "eps": ({"eps_trailing": 1.0}, 10), "eg": ({"earnings_growth": 20}, 8),
    "rg": ({"revenue_growth": 10}, 8), "pe": ({"pe_ratio": 15}, 7), "de": ({"debt_to_equity": 10}, 7),
    "roe": ({"roe": 20}, 7), "tp": ({"target_price": 120.0}, 8),
}
MA_TRIO = {"ma50": 90.0, "ma200": 80.0}        # above 50dma (8) + above 200dma (10) + golden cross (10)


def srow(names=(), ma=False, **extra):
    row = {"last_price": 100.0}
    if ma:
        row.update(MA_TRIO)
    for n in names:
        row.update(FACTORS[n][0])
    row.update(extra)
    return row


@pytest.mark.parametrize("name", list(FACTORS))
def test_sarvas_each_factor_alone(name):
    assert gs.sarvas_signal(srow([name]), 0)[0] == FACTORS[name][1]


def test_sarvas_ma_components_and_pegu_bonus():
    assert gs.sarvas_signal(srow(ma=True), 0)[0] == 28
    assert gs.sarvas_signal({"last_price": 100, "ma50": 90}, 0)[0] == 8
    assert gs.sarvas_signal({"last_price": 100, "ma200": 90}, 0)[0] == 10
    assert gs.sarvas_signal({"last_price": 50, "ma50": 90, "ma200": 80}, 0)[0] == 10   # golden cross only
    assert gs.sarvas_signal({}, 0) == (0, "SELL")
    assert gs.sarvas_signal({}, 59.9)[0] == 0
    assert gs.sarvas_signal({}, 60)[0] == 5


def test_sarvas_factor_boundaries():
    s = lambda **r: gs.sarvas_signal(dict({"last_price": 100.0}, **r), 0)[0]  # noqa: E731
    assert s(rsi_14=35) == 7 and s(rsi_14=68) == 7 and s(rsi_14=34.99) == 0 and s(rsi_14=68.01) == 0
    assert s(volume_ratio=1.5) == 0 and s(volume_ratio=1.51) == 5
    assert s(week52_high=111.11) == 7 and s(week52_high=111.12) == 0           # ltp >= 0.9 * high
    assert s(earnings_growth=10) == 0 and s(revenue_growth=5) == 0
    assert s(pe_ratio=5) == 0 and s(pe_ratio=30) == 0 and s(pe_ratio=5.01) == 7 and s(pe_ratio=29.99) == 7
    assert s(debt_to_equity=0) == 7 and s(debt_to_equity=49.9) == 7 and s(debt_to_equity=50) == 0
    assert s(roe=15) == 0 and s(target_price=110.0) == 0 and s(target_price=110.01) == 8
    assert s(macd=0) == 0 and s(eps_trailing=0) == 0


SIGNAL_CASES = [
    (80, "STRONG BUY", ("rsi", "macd", "h52", "eps", "eg", "rg", "pe"), True),
    (79, "BUY", ("rsi", "macd", "vr", "h52", "eps", "eg", "rg", "pe", "de", "roe", "tp"), False),
    (65, "BUY", ("rsi", "macd", "vr", "h52", "eps", "eg", "rg", "pe", "tp"), False),
    (64, "ACCUMULATE", ("rsi", "macd", "vr", "h52", "eps", "eg", "rg", "pe", "de"), False),
    (50, "ACCUMULATE", ("rsi", "macd", "vr", "h52", "eps", "eg", "rg"), False),
    (49, "HOLD", ("rsi", "macd", "vr", "h52", "eps", "eg", "pe"), False),
    (35, "HOLD", ("rsi", "macd", "vr", "eps", "eg"), False),
    (34, "REDUCE", ("eps", "eg", "rg", "tp"), False),
    (20, "REDUCE", ("rsi", "macd", "eg"), False),
    (19, "SELL", ("rsi", "macd", "h52"), False),
]


@pytest.mark.parametrize("pts,signal,names,ma", SIGNAL_CASES, ids=[f"{c[0]}-{c[1]}" for c in SIGNAL_CASES])
def test_sarvas_signal_thresholds(pts, signal, names, ma):
    assert gs.sarvas_signal(srow(names, ma=ma), 0) == (pts, signal)


# ---- load_universe -----------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "DATA_DIR", tmp_path)
    return tmp_path


def test_load_universe_india_csv(data_dir, capsys):
    (data_dir / "india_tickers_full.csv").write_text(
        "Symbol,Suffix,LTP,Change%,Darvas_Signal\nTCS,.NS,100,1.5,BUY\nINFY,,200,-1,HOLD\n500325,.BO,50,0,NA\n")
    u = gs.load_universe()
    assert u["yf_symbol"].tolist() == ["TCS.NS", "INFY.NS", "500325.BO"]
    assert set(u["market"]) == {"IN"}
    assert {"symbol", "last_price", "suffix", "change_pct", "darvas_signal"} <= set(u.columns)
    assert "[UNIVERSE] India: 3 tickers" in capsys.readouterr().out


def test_load_universe_extended_json_suffixes_and_dedupe(data_dir):
    (data_dir / "global_universe.json").write_text(json.dumps({
        "US": ["AAPL", "AAPL"], "JP": ["7203"], "CN_SSE": ["600519"], "HK_main": ["0700"], "XX": ["ZZZ"]}))
    u = gs.load_universe().set_index("yf_symbol")
    assert list(u.index) == ["AAPL", "7203.T", "600519.SS", "0700.HK", "ZZZ"]
    assert (u.index == "AAPL").sum() == 1                                      # duplicate collapsed
    assert u.loc["7203.T", "market"] == "JP" and u.loc["0700.HK", "market"] == "HK"
    assert u.loc["ZZZ", "suffix"] == ""                                       # unknown market -> no suffix


def test_load_universe_nothing_available_raises(data_dir):
    with pytest.raises(RuntimeError, match="No ticker source found"):
        gs.load_universe()


def test_load_universe_international_block_when_markets_registry_exists(data_dir, monkeypatch):
    # The branch is dead today (see the xfail below); give it the registry it expects to pin its row-building.
    import global_tickers
    monkeypatch.setattr(global_tickers, "MARKETS", {
        "IN": {"suffix": ".NS", "tickers": ["SKIP"], "exchange": "NSE", "currency": "INR"},
        "JP": {"suffix": ".T", "tickers": ["7203", "6758"], "exchange": "TSE", "currency": "JPY",
               "extra": {"suffix": ".OS", "tickers": ["1301"]}},
    }, raising=False)
    u = gs.load_universe().set_index("yf_symbol")
    assert list(u.index) == ["7203.T", "6758.T", "1301.OS"]                 # IN is skipped (comes from the CSV)
    assert u.loc["1301.OS", "suffix"] == ".OS" and u.loc["7203.T", "currency"] == "JPY"
    assert set(u["market"]) == {"JP"} and u.loc["6758.T", "exchange"] == "TSE"


@pytest.mark.xfail(strict=True, raises=RuntimeError,
                   reason="load_universe does `from global_tickers import MARKETS`, but global_tickers.py has no "
                          "MARKETS (it lives in universe_builder.py); the ImportError is swallowed, so the "
                          "'550 curated international tickers' source never loads")
def test_load_universe_international_tickers_from_global_tickers(data_dir):
    u = gs.load_universe()
    assert "JP" in set(u["market"])


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="the extended source iterates `for sym in syms` expecting {market: [symbols]}, but "
                          "data/global_universe.json (written by universe_builder.save_universe) is "
                          "{code: {name, exchange, yf_symbols, count, source}}; iterating a dict yields its keys, "
                          "so the universe is filled with the symbols 'name', 'exchange', 'yf_symbols', ...")
def test_load_universe_reads_the_file_universe_builder_writes(data_dir):
    (data_dir / "global_universe.json").write_text(json.dumps({
        "US": {"name": "United States", "exchange": "NYSE", "yf_symbols": ["AAPL", "MSFT"], "count": 2, "source": "x"}}))
    u = gs.load_universe()
    assert sorted(u["yf_symbol"]) == ["AAPL", "MSFT"]


# ---- fetch_batch -------------------------------------------------------------------------

class FakeYF:
    def __init__(self, raw=None, info=None, download_error=None):
        self._raw, self._info, self._err = raw, info or {}, download_error
        self.calls = []

    def download(self, symbols, **kw):
        self.calls.append((symbols, kw))
        if self._err:
            raise self._err
        return self._raw

    def Ticker(self, sym):                                         # noqa: N802 (mirrors yfinance API)
        info = self._info
        if isinstance(info, Exception):
            raise info
        return types.SimpleNamespace(info=info.get(sym) if isinstance(info, dict) and sym in info else info)


def multi_frame(series_by_sym, volume=None):
    cols = {}
    for sym, closes in series_by_sym.items():
        idx = pd.bdate_range("2025-01-01", periods=len(closes))
        cols[("Close", sym)] = pd.Series(closes, index=idx, dtype=float)
        cols[("Volume", sym)] = pd.Series(volume if volume is not None else [1000.0] * len(closes), index=idx)
    df = pd.DataFrame(cols)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


@pytest.fixture
def yf_installed(monkeypatch):
    def install(fake):
        monkeypatch.setattr(gs, "_YF", True)
        monkeypatch.setattr(gs, "yf", fake, raising=False)
        return fake
    return install


def test_fetch_batch_returns_empty_without_yfinance(monkeypatch):
    monkeypatch.setattr(gs, "_YF", False)
    assert gs.fetch_batch(["AAA"]) == {}


def test_fetch_batch_technicals(yf_installed):
    closes = list(range(1, 261))                       # 1..260, strictly rising
    vol = [1000.0] * 259 + [3000.0]
    fake = yf_installed(FakeYF(multi_frame({"AAA": closes}, volume=vol)))
    out = gs.fetch_batch(["AAA"], period="2y")
    r = out["AAA"]
    assert fake.calls[0][1]["period"] == "2y" and fake.calls[0][1]["progress"] is False
    assert r["last_price"] == 260.0
    assert r["ma50"] == 235.5 and r["ma200"] == 160.5               # means of 211..260 and 61..260
    assert r["week52_high"] == 260.0 and r["week52_low"] == 9.0      # last 252 closes: 9..260
    assert r["volume_ratio"] == round(3000 / ((1000 * 19 + 3000) / 20), 3)
    assert r["pct_above_50dma"] == round((260 / 235.5 - 1) * 100, 2)
    assert r["pct_above_200dma"] == round((260 / 160.5 - 1) * 100, 2)
    assert r["pct_from_52w_high"] == 0.0
    assert r["macd"] > 0
    assert np.isnan(r["rsi_14"])                                    # no down days -> undefined RSI


def test_fetch_batch_rsi_value(yf_installed):
    closes = [100.0]
    for i in range(259):
        closes.append(closes[-1] + (3 if i % 2 == 0 else -1))
    yf_installed(FakeYF(multi_frame({"AAA": closes})))
    assert gs.fetch_batch(["AAA"])["AAA"]["rsi_14"] == 75.0         # 7 x +3 / 7 x -1 in the last 14 moves


def test_fetch_batch_skips_short_history_and_missing_symbols(yf_installed):
    frame = multi_frame({"LONG": list(range(1, 261)), "SHORT": list(range(1, 20))})
    frame.loc[frame.index[19:], ("Close", "SHORT")] = np.nan
    yf_installed(FakeYF(frame))
    out = gs.fetch_batch(["LONG", "SHORT", "MISSING"])
    assert set(out) == {"LONG"}


def test_fetch_batch_exactly_twenty_rows_is_enough(yf_installed):
    yf_installed(FakeYF(multi_frame({"A": [float(i + 1) for i in range(20)]})))
    assert "A" in gs.fetch_batch(["A"])
    yf_installed(FakeYF(multi_frame({"A": [float(i + 1) for i in range(19)]})))
    assert gs.fetch_batch(["A"]) == {}


def test_fetch_batch_download_failures(yf_installed):
    yf_installed(FakeYF(download_error=RuntimeError("rate limited")))
    assert gs.fetch_batch(["A"]) == {}
    yf_installed(FakeYF(raw=pd.DataFrame()))
    assert gs.fetch_batch(["A"]) == {}


def test_fetch_batch_fundamentals_merge(yf_installed):
    info = {"AAA": {"trailingPE": 12.0, "priceToBook": 2.0, "pegRatio": 1.1, "returnOnEquity": 0.18,
                    "operatingMargins": 0.25, "debtToEquity": 40.0, "currentRatio": 1.7, "trailingEps": 5.0,
                    "forwardEps": 6.0, "revenueGrowth": 0.12, "earningsGrowth": 0.2, "dividendYield": 0.03,
                    "beta": 0.9, "marketCap": 10**9, "targetMeanPrice": 300.0, "sector": "Tech", "industry": "SW",
                    "longName": "Alpha Corp", "shortName": "Alpha"}}
    yf_installed(FakeYF(multi_frame({"AAA": list(range(1, 261))}), info=info))
    r = gs.fetch_batch(["AAA"])["AAA"]
    assert (r["pe_ratio"], r["pb_ratio"], r["peg_ratio"]) == (12.0, 2.0, 1.1)
    assert (r["roe"], r["operating_margins"], r["dividend_yield"]) == (18.0, 25.0, 3.0)
    assert (r["revenue_growth"], r["earnings_growth"]) == (12.0, 20.0)
    assert (r["debt_to_equity"], r["current_ratio"], r["beta"], r["market_cap"]) == (40.0, 1.7, 0.9, 10**9)
    assert (r["eps_trailing"], r["eps_forward"], r["target_price"]) == (5.0, 6.0, 300.0)
    assert (r["sector"], r["industry"], r["name"]) == ("Tech", "SW", "Alpha Corp")
    assert r["last_price"] == 260.0                                  # technicals kept


def test_fetch_batch_name_falls_back_to_short_name_and_info_errors_keep_prices(yf_installed):
    yf_installed(FakeYF(multi_frame({"AAA": list(range(1, 261))}), info={"AAA": {"shortName": "Alpha"}}))
    r = gs.fetch_batch(["AAA"])["AAA"]
    assert r["name"] == "Alpha" and r["pe_ratio"] is None
    yf_installed(FakeYF(multi_frame({"AAA": list(range(1, 261))}), info=RuntimeError("boom")))
    r = gs.fetch_batch(["AAA"])["AAA"]
    assert r["last_price"] == 260.0 and "pe_ratio" not in r


# ---- scan_universe -----------------------------------------------------------------------

@pytest.fixture
def reports(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(gs.time, "sleep", lambda s: None)
    monkeypatch.setattr(gs, "DATE_LABEL", "20260101")
    return tmp_path / "reports"


def universe_df():
    return pd.DataFrame({
        "yf_symbol": ["AAA", "BBB", "CCC", "DDD"], "market": ["US", "US", "JP", "IN"],
        "symbol": ["AAA", "BBB", "CCC", "DDD"],
        "pe_ratio": [12, 25, None, 40], "roe": [22, 5, None, 8], "last_price": [100.0, 50.0, 10.0, 5.0]})


def test_scan_universe_mock_scores_and_writes_per_market(reports):
    res = gs.scan_universe(universe_df(), mock=True)
    out = reports / "global_scan_20260101"
    assert sorted(p.name for p in out.glob("*_scan.csv")) == ["IN_scan.csv", "JP_scan.csv", "US_scan.csv"]
    assert len(res) == 4
    assert res["pegu_score"].is_monotonic_decreasing                    # sorted by Pegu, best first
    assert (res["data_source"] == "local").all()
    assert {"pegu_grade", "sarvas_score", "sarvas_signal", "scan_date"} <= set(res.columns)
    assert json.loads((out / "checkpoint.json").read_text()) == {
        "IN": {"tickers": 1, "ts": gs.TODAY}, "JP": {"tickers": 1, "ts": gs.TODAY}, "US": {"tickers": 2, "ts": gs.TODAY}}
    aaa = res[res["yf_symbol"] == "AAA"].iloc[0]
    assert (aaa["pegu_score"], aaa["pegu_grade"]) == gs.pegu_score(universe_df().iloc[0].to_dict())
    assert (aaa["sarvas_score"], aaa["sarvas_signal"]) == gs.sarvas_signal(universe_df().iloc[0].to_dict(), aaa["pegu_score"])


def test_scan_universe_market_filter_and_empty(reports):
    res = gs.scan_universe(universe_df(), markets=["JP"], mock=True)
    assert res["market"].tolist() == ["JP"]
    assert gs.scan_universe(universe_df(), markets=["ZZ"], mock=True).empty


def test_scan_universe_resume_uses_checkpoint(reports, capsys):
    gs.scan_universe(universe_df(), markets=["US"], mock=True)
    out = reports / "global_scan_20260101"
    pd.DataFrame({"yf_symbol": ["MARK"], "market": ["US"], "pegu_score": [1.0]}).to_csv(out / "US_scan.csv", index=False)
    res = gs.scan_universe(universe_df(), markets=["US"], mock=True, resume=True)
    assert res["yf_symbol"].tolist() == ["MARK"]                        # read from the checkpointed CSV, not recomputed
    assert "US: loaded from checkpoint" in capsys.readouterr().out
    # without --resume the market is scanned again and the CSV is overwritten
    res = gs.scan_universe(universe_df(), markets=["US"], mock=True, resume=False)
    assert sorted(res["yf_symbol"]) == ["AAA", "BBB"]


def test_scan_universe_resume_with_missing_csv_rescans(reports):
    out = reports / "global_scan_20260101"
    out.mkdir(parents=True)
    (out / "checkpoint.json").write_text(json.dumps({"US": {"tickers": 2, "ts": "x"}}))
    res = gs.scan_universe(universe_df(), markets=["US"], mock=True, resume=True)
    assert sorted(res["yf_symbol"]) == ["AAA", "BBB"]


def test_scan_universe_live_path_batches_and_labels_sources(reports, monkeypatch):
    monkeypatch.setattr(gs, "_YF", True)
    batches = []

    def fake_fetch(batch, period="1y"):
        batches.append(list(batch))
        return {s: {"last_price": 100.0, "pe_ratio": 12.0, "roe": 22.0} for s in batch if s != "BBB"}

    monkeypatch.setattr(gs, "fetch_batch", fake_fetch)
    res = gs.scan_universe(universe_df(), markets=["US"], batch_size=1, workers=2)
    assert sorted(map(tuple, batches)) == [("AAA",), ("BBB",)]
    src = res.set_index("yf_symbol")["data_source"].to_dict()
    assert src == {"AAA": "live", "BBB": "no_data"}


def test_scan_universe_falls_back_to_local_when_yfinance_missing(reports, monkeypatch):
    monkeypatch.setattr(gs, "_YF", False)
    monkeypatch.setattr(gs, "fetch_batch", lambda *a, **k: pytest.fail("must not fetch"))
    res = gs.scan_universe(universe_df(), markets=["IN"])
    assert res["data_source"].tolist() == ["local"]


# ---- export_excel ------------------------------------------------------------------------

def results_df():
    df = pd.DataFrame({
        "yf_symbol": ["A", "B", "C"], "market": ["US", "US", "IN"], "name": ["a", "b", "c"], "sector": ["x", "y", None],
        "last_price": [1.0, 2.0, 3.0], "pegu_score": [90.0, 70.0, 20.0], "pegu_grade": ["A+", "A", "F"],
        "sarvas_score": [85, 66, 10], "sarvas_signal": ["STRONG BUY", "BUY", "SELL"],
        "data_source": ["live", "live", "no_data"]})
    return df


def test_export_excel_sheets_and_numbers(reports, tmp_path):
    from openpyxl import load_workbook
    reports.mkdir(parents=True)
    path = gs.export_excel(results_df(), reports)
    assert path.name == "Global_Research_20260101.xlsx" and path.exists()
    wb = load_workbook(path)
    assert wb.sheetnames == ["Summary", "Top 500 (Pegu)", "Strong Buy & Buy", "By Market", "All Tickers"]
    summary = {wb["Summary"].cell(r, 1).value: wb["Summary"].cell(r, 2).value for r in range(3, 21)}
    assert summary["Total Tickers Scanned"] == 3 and summary["Markets Covered"] == 2
    assert summary["Data With Live Prices"] == 2 and summary["Avg Pegu Score"] == 60.0
    assert summary["Grade A+ (≥80)"] == 1 and summary["Grade F  (<25)"] == 1
    assert summary["STRONG BUY Signals"] == 1 and summary["BUY Signals"] == 1 and summary["SELL Signals"] == 1
    top = wb["Top 500 (Pegu)"]
    assert [c.value for c in top[1]][:3] == ["yf_symbol", "market", "name"]
    assert top.max_row == 4
    assert top.cell(2, 1).value == "A"
    grade_col = [c.value for c in top[1]].index("pegu_grade") + 1
    assert top.cell(2, grade_col).fill.fgColor.rgb.endswith("00B050")        # A+ colour
    buys = wb["Strong Buy & Buy"]
    assert buys.max_row == 3                                                  # header + STRONG BUY + BUY
    by_mkt = wb["By Market"]
    rows = {by_mkt.cell(r, 1).value: [by_mkt.cell(r, c).value for c in range(2, 10)] for r in (2, 3)}
    assert rows["IN"] == [1, 20.0, 0, 0, 0, 0, 0, 1]
    assert rows["US"] == [2, 80.0, 1, 1, 0, 2, 0, 0]
    assert wb["All Tickers"].max_row == 4
    assert wb["All Tickers"].cell(4, 4).value is None                         # NaN/None written as blank


def test_export_excel_none_cases(reports, monkeypatch):
    assert gs.export_excel(pd.DataFrame(), reports) is None
    monkeypatch.setattr(gs, "_XL", False)
    assert gs.export_excel(results_df(), reports) is None


# ---- main ------------------------------------------------------------------------------

def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["global_scanner", *argv])
    gs.main()


def test_main_runs_scan_and_writes_outputs(reports, monkeypatch, capsys):
    calls = {}
    real_scan = gs.scan_universe
    monkeypatch.setattr(gs, "load_universe", lambda: universe_df())

    def fake_scan(universe, **kw):
        calls.update(kw)
        return real_scan(universe, markets=kw["markets"], mock=True)

    monkeypatch.setattr(gs, "scan_universe", fake_scan)
    exported = []
    monkeypatch.setattr(gs, "export_excel", lambda df, out: exported.append((len(df), out)))
    run_main(monkeypatch, "--markets", "US", "JP", "--batch-size", "7", "--workers", "3", "--mock", "--resume")
    assert calls == {"markets": ["US", "JP"], "batch_size": 7, "workers": 3, "mock": True, "resume": True}
    assert exported == [(3, reports / "global_scan_20260101")]
    assert (reports / "Global_Research_20260101.csv").exists()
    out = capsys.readouterr().out
    assert "[RESULTS] 3 stocks scored" in out and "[CSV]   Saved" in out


def test_main_defaults_and_empty_results(reports, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(gs, "load_universe", lambda: universe_df())
    monkeypatch.setattr(gs, "scan_universe", lambda u, **kw: seen.update(kw) or pd.DataFrame())
    run_main(monkeypatch)
    assert seen == {"markets": None, "batch_size": 50, "workers": 4, "mock": False, "resume": False}
    assert "[WARN] No results produced." in capsys.readouterr().out
    assert not (reports / "Global_Research_20260101.csv").exists()


def test_main_excel_only_reads_existing_csvs(reports, monkeypatch, capsys):
    out = reports / "global_scan_20260101"
    out.mkdir(parents=True)
    pd.DataFrame({"yf_symbol": ["A"], "market": ["US"], "pegu_score": [10.0], "pegu_grade": ["F"]}).to_csv(out / "US_scan.csv", index=False)
    pd.DataFrame({"yf_symbol": ["B"], "market": ["IN"], "pegu_score": [75.0], "pegu_grade": ["A"],
                  "sarvas_signal": ["BUY"]}).to_csv(out / "IN_scan.csv", index=False)
    monkeypatch.setattr(gs, "load_universe", lambda: universe_df())
    monkeypatch.setattr(gs, "scan_universe", lambda *a, **k: pytest.fail("scan must be skipped"))
    exported = []
    monkeypatch.setattr(gs, "export_excel", lambda df, o: exported.append(df["yf_symbol"].tolist()))
    run_main(monkeypatch, "--excel-only")
    assert exported == [["B", "A"]]                                        # sorted by Pegu, descending
    printed = capsys.readouterr().out
    assert "Top 20 by Pegu Score" in printed and "B" in printed
