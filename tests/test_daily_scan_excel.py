"""daily_scan_excel: Pegu / Sarvas scoring, data cascade, live fetchers (faked) and the Excel workbook."""
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

import daily_scan_excel as ds


def col(values, **kw):
    return pd.Series(values, **kw)


# ---- small helpers -------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (1, 1.0), ("2.5", 2.5), (0, 0.0), (None, None), ("x", None), (float("nan"), None),
    (float("inf"), None), (float("-inf"), None),
])
def test_safe_float(value, expected):
    assert ds._safe_float(value) == expected


def test_safe_float_default():
    assert ds._safe_float(None, default=-1) == -1
    assert ds._safe_float("bad", default=0.0) == 0.0
    assert ds._safe_float(float("nan"), default=7) == 7


def test_score_breakpoints_and_nan():
    bp = [(0, 0), (10, 4), (20, 8), (float("inf"), 1)]
    assert ds._score(-1, bp) == 0 and ds._score(0, bp) == 4 and ds._score(10, bp) == 8 and ds._score(20, bp) == 1
    assert ds._score(float("nan"), bp) == 1 and ds._score(None, bp) == 1


# ---- _normalise_live -----------------------------------------------------------------------

def test_normalise_live_scales_fractions_only():
    df = pd.DataFrame({"roe": [0.18, 18.0, -0.5, np.nan, 1.99, 2.0], "last_price": [100.0] * 6,
                       "ma_50": [80.0] * 6, "ma_200": [50.0] * 6, "w52_high": [125.0] * 6,
                       "target_price": [110.0] * 6})
    out = ds._normalise_live(df)
    assert out["roe_pct"].tolist()[:3] == [18.0, 18.0, -50.0]
    assert np.isnan(out["roe_pct"][3]) and out["roe_pct"][4] == pytest.approx(199.0) and out["roe_pct"][5] == 2.0
    assert out["pct_above_50dma"][0] == 25.0 and out["pct_above_200dma"][0] == 100.0
    assert out["pct_from_52w_high"][0] == -20.0
    assert out["upside_pct"][0] == 10.0
    assert (out["fetch_date"] == ds.TODAY).all()
    for c in ("operating_margins_pct", "revenue_growth_pct", "earnings_growth_pct", "dividend_yield_pct"):
        assert out[c].isna().all()                     # source columns absent -> NaN placeholders


def test_normalise_live_keeps_existing_columns():
    df = pd.DataFrame({"last_price": [10.0], "operating_margins_pct": [12.0], "upside_pct": [3.0],
                       "pct_above_50dma": [1.0], "fetch_date": ["2020-01-01"]})
    out = ds._normalise_live(df)
    assert out["operating_margins_pct"][0] == 12.0 and out["upside_pct"][0] == 3.0
    assert out["pct_above_50dma"][0] == 1.0 and out["fetch_date"][0] == "2020-01-01"
    assert out["pct_above_200dma"].isna().all()


# ---- load_or_generate_data -------------------------------------------------------------------

def test_mock_data_is_the_sample_set(tmp_path):
    df = ds.load_or_generate_data(str(tmp_path), use_mock=True)
    assert len(df) == len(ds._SAMPLE_STOCKS)
    assert list(df.columns[:len(ds.COLUMNS)]) == ds.COLUMNS
    assert df["last_price"].dtype.kind == "f"                      # string prices ("3520") coerced to float
    assert df["pe_ratio"].dtype.kind == "f"
    first = df.iloc[0]
    assert first["symbol"] == "RELIANCE"
    assert first["roe_pct"] == first["roe"]
    assert first["pct_above_50dma"] == round((first["last_price"] / first["ma_50"] - 1) * 100, 2)
    assert first["upside_pct"] == round((first["target_price"] / first["last_price"] - 1) * 100, 2)
    assert (df["fetch_date"] == ds.TODAY).all()
    assert not os.listdir(tmp_path)                                 # mock mode writes nothing


def test_extractor_csv_is_preferred_when_populated(tmp_path, monkeypatch):
    rows = pd.DataFrame({"symbol": list("ABCDEFG"), "exchange": ["NSE"] * 7, "last_price": [1.0] * 7, "roe": [0.2] * 7})
    rows.to_csv(tmp_path / "all_stocks_combined.csv", index=False)
    monkeypatch.setattr(ds, "fetch_live_nse_data", lambda s: pytest.fail("no live fetch expected"))
    df = ds.load_or_generate_data(str(tmp_path), use_mock=False)
    assert len(df) == 7 and df["roe_pct"][0] == 20.0


def test_extractor_csv_needs_more_than_five_prices(tmp_path, monkeypatch):
    rows = pd.DataFrame({"symbol": list("ABCDE"), "exchange": ["NSE"] * 5, "last_price": [1.0] * 5})
    rows.to_csv(tmp_path / "all_stocks_combined.csv", index=False)
    monkeypatch.setattr(ds, "fetch_live_nse_data", lambda s: pd.DataFrame())
    monkeypatch.setattr(ds, "fetch_live_bse_data", lambda s: pd.DataFrame())
    df = ds.load_or_generate_data(str(tmp_path), use_mock=False)
    assert len(df) == len(ds._SAMPLE_STOCKS)                         # fell all the way back to the sample


def test_mock_ignores_extractor_csv(tmp_path):
    pd.DataFrame({"symbol": list("ABCDEFG"), "last_price": [1.0] * 7}).to_csv(tmp_path / "all_stocks_combined.csv", index=False)
    assert len(ds.load_or_generate_data(str(tmp_path), use_mock=True)) == len(ds._SAMPLE_STOCKS)


def test_live_cascade_enriches_normalises_and_caches(tmp_path, monkeypatch):
    nse = pd.DataFrame({"symbol": ["AAA"], "exchange": ["NSE"], "last_price": [100.0]})
    bse = pd.DataFrame({"symbol": ["500"], "exchange": ["BSE"], "last_price": [50.0]})
    monkeypatch.setattr(ds, "fetch_live_nse_data", lambda s: nse)
    monkeypatch.setattr(ds, "fetch_live_bse_data", lambda s: bse)
    monkeypatch.setattr(ds, "enrich_with_yfinance", lambda d: d.assign(roe=0.1))
    target = tmp_path / "nested" / "data"
    df = ds.load_or_generate_data(str(target), use_mock=False)
    assert df["symbol"].tolist() == ["AAA", "500"] and df["roe_pct"].tolist() == [10.0, 10.0]
    assert (target / "all_stocks_combined.csv").exists()


def test_live_cascade_uses_one_source_when_other_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "fetch_live_nse_data", lambda s: pd.DataFrame())
    monkeypatch.setattr(ds, "fetch_live_bse_data", lambda s: pd.DataFrame({"symbol": ["500"], "exchange": ["BSE"], "last_price": [5.0]}))
    monkeypatch.setattr(ds, "enrich_with_yfinance", lambda d: d)
    assert ds.load_or_generate_data(str(tmp_path), use_mock=False)["symbol"].tolist() == ["500"]


# ---- live fetchers (faked libraries) ----------------------------------------------------------

def test_fetch_live_nse(monkeypatch):
    def nse_eq(sym):
        if sym == "BAD":
            raise RuntimeError("nope")
        return {"priceInfo": {"lastPrice": "101.5", "weekHighLow": {"max": 150, "min": "90"}},
                "metadata": {"companyName": f"{sym} Ltd", "industry": "IT"}, "industryInfo": {"pe": "12.5"}}

    monkeypatch.setitem(sys.modules, "nsepython", types.SimpleNamespace(nse_eq=nse_eq))
    df = ds.fetch_live_nse_data(["AAA", "BAD", "CCC"])
    assert df["symbol"].tolist() == ["AAA", "CCC"]
    r = df.iloc[0]
    assert (r["exchange"], r["company_name"], r["sector"], r["last_price"]) == ("NSE", "AAA Ltd", "IT", 101.5)
    assert (r["w52_high"], r["w52_low"], r["pe_ratio"]) == (150.0, 90.0, 12.5)


def test_fetch_live_nse_missing_library(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "nsepython", None)
    assert ds.fetch_live_nse_data(["A"]).empty
    assert "nsepython not installed" in capsys.readouterr().out


def test_fetch_live_bse(monkeypatch):
    class BSE:
        def getQuote(self, code):                        # noqa: N802
            if code == "1":
                return {}
            if code == "2":
                raise RuntimeError("down")
            return {"companyName": "X", "industry": "Y", "currentValue": "10", "ttmPe": "5", "pbv": "1.1", "ttmEps": "2",
                    "weeks52High": "12", "weeks52Low": "8", "marketCapFull": "1000", "dividendYield": "1.5", "bookValue": "9"}

    mod = types.ModuleType("bsedata.bse")
    mod.BSE = BSE
    monkeypatch.setitem(sys.modules, "bsedata", types.ModuleType("bsedata"))
    monkeypatch.setitem(sys.modules, "bsedata.bse", mod)
    df = ds.fetch_live_bse_data(["1", "2", "500325"])
    assert len(df) == 1
    r = df.iloc[0]
    assert (r["symbol"], r["exchange"], r["last_price"], r["pe_ratio"], r["pb_ratio"]) == ("500325", "BSE", 10.0, 5.0, 1.1)
    assert (r["eps_trailing"], r["w52_high"], r["w52_low"], r["market_cap"]) == (2.0, 12.0, 8.0, 1000.0)
    monkeypatch.setitem(sys.modules, "bsedata.bse", None)
    assert ds.fetch_live_bse_data(["1"]).empty


def fake_yf(info=None, closes=None, volume=None, raises=False):
    idx = pd.bdate_range("2025-01-01", periods=len(closes)) if closes is not None else None

    class T:
        def __init__(self, sym):
            self.sym = sym
            if raises:
                raise RuntimeError("blocked")
            self.info = info or {}

        def history(self, period):
            return pd.DataFrame({"Close": closes, "Volume": volume if volume is not None else [1000.0] * len(closes)}, index=idx)

    return types.SimpleNamespace(Ticker=T)


def test_enrich_with_yfinance_fundamentals_and_technicals(monkeypatch):
    closes = [100.0]
    for i in range(259):
        closes.append(closes[-1] + (3 if i % 2 == 0 else -1))
    info = {"trailingPE": 12.0, "priceToBook": 2.0, "roe": None, "returnOnEquity": 0.2, "beta": 0.9,
            "fiftyTwoWeekHigh": 500.0, "longName": "Alpha", "sector": "Tech", "marketCap": float("nan")}
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf(info, closes))
    out = ds.enrich_with_yfinance(pd.DataFrame({"symbol": ["AAA", "500"], "exchange": ["NSE", "BSE"]}))
    r = out.iloc[0]
    assert (r["pe_ratio"], r["pb_ratio"], r["roe"], r["beta"], r["w52_high"]) == (12.0, 2.0, 0.2, 0.9, 500.0)
    assert (r["company_name"], r["sector"]) == ("Alpha", "Tech")
    assert "market_cap" not in out.columns or pd.isna(r.get("market_cap"))      # NaN info values are not copied
    assert r["rsi_14"] == 75.0 and r["macd"] != 0
    assert r["ma_50"] == pytest.approx(float(pd.Series(closes).tail(50).mean()))
    assert r["ma_200"] == pytest.approx(float(pd.Series(closes).tail(200).mean()))
    assert r["volume_ratio"] == 1.0
    assert r["return_1m_pct"] == round((closes[-1] / closes[-20] - 1) * 100, 2)
    assert r["return_3m_pct"] == round((closes[-1] / closes[-63] - 1) * 100, 2)
    assert r["return_6m_pct"] == round((closes[-1] / closes[-126] - 1) * 100, 2)


def test_enrich_short_history_skips_ma200_and_returns(monkeypatch):
    closes = [100.0 + i for i in range(70)]
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf({}, closes))
    r = ds.enrich_with_yfinance(pd.DataFrame({"symbol": ["A"], "exchange": ["NSE"]})).iloc[0]
    assert "ma_200" not in r.index and r["ma_50"] == pytest.approx(np.mean(closes[-50:]))
    assert r["return_1m_pct"] == round((closes[-1] / closes[-20] - 1) * 100, 2)
    assert r["return_3m_pct"] == round((closes[-1] / closes[-63] - 1) * 100, 2) and "return_6m_pct" not in r.index
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf({}, closes[:49]))
    r = ds.enrich_with_yfinance(pd.DataFrame({"symbol": ["A"], "exchange": ["NSE"]})).iloc[0]
    assert "ma_50" not in r.index                                        # fewer than 50 bars -> no technicals


def test_enrich_errors_keep_the_row_and_missing_library(monkeypatch):
    base = pd.DataFrame({"symbol": ["A"], "exchange": ["NSE"], "last_price": [5.0]})
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf(raises=True, closes=[1.0]))
    out = ds.enrich_with_yfinance(base)
    assert out["last_price"][0] == 5.0 and list(out.columns) == list(base.columns)
    monkeypatch.setitem(sys.modules, "yfinance", None)
    assert ds.enrich_with_yfinance(base) is base


def test_enrich_suffix_by_exchange(monkeypatch):
    seen = []

    class T:
        def __init__(self, sym):
            seen.append(sym)
            self.info = {}

        def history(self, period):
            return pd.DataFrame({"Close": [], "Volume": []})

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=T))
    ds.enrich_with_yfinance(pd.DataFrame({"symbol": ["A", "500"], "exchange": ["NSE", "BSE"]}))
    assert seen == ["A.NS", "500.BO"]


# ---- Pegu scoring ----------------------------------------------------------------------------

def base_df(**cols):
    n = max(len(v) for v in cols.values())
    df = pd.DataFrame({c: [np.nan] * n for c in (
        "pe_ratio", "peg_ratio", "pb_ratio", "roe_pct", "operating_margins_pct", "debt_equity", "earnings_growth_pct",
        "revenue_growth_pct", "eps_forward", "current_ratio", "dividend_yield_pct", "beta")})
    for k, v in cols.items():
        df[k] = v
    return df


NAN = float("nan")
COMPONENTS = [
    ("pe_ratio", "pe_score", [(NAN, 3), (-5, 3), (0, 3), (7.9, 10), (8, 9), (11.9, 9), (12, 7), (15.9, 7), (16, 5), (21.9, 5),
                              (22, 3), (29.9, 3), (30, 1), (49.9, 1), (50, 0), (1000, 0)]),
    ("peg_ratio", "peg_score", [(NAN, 4), (-1, 0), (0, 0), (0.49, 10), (0.5, 8), (0.99, 8), (1.0, 5), (1.49, 5), (1.5, 2),
                                (1.99, 2), (2.0, 0), (9, 0)]),
    ("pb_ratio", "pb_score", [(NAN, 3), (-1, 3), (0, 3), (0.9, 10), (1, 8), (1.9, 8), (2, 6), (2.9, 6), (3, 4), (4.9, 4),
                              (5, 2), (9.9, 2), (10, 0)]),
    ("roe_pct", "roe_score", [(NAN, 3), (36, 10), (35, 9), (26, 9), (25, 7), (21, 7), (20, 5), (16, 5), (15, 3), (11, 3),
                              (10, 1), (1, 1), (0, 0), (-5, 0)]),
    ("operating_margins_pct", "margin_score", [(NAN, 3), (36, 10), (35, 8), (26, 8), (25, 6), (19, 6), (18, 4), (13, 4),
                                               (12, 2), (7, 2), (6, 1), (1, 1), (0, 0), (-3, 0)]),
    ("debt_equity", "debt_score", [(NAN, 4), (0, 10), (0.05, 9), (0.1, 8), (0.29, 8), (0.3, 7), (0.49, 7), (0.5, 5), (0.99, 5),
                                   (1.0, 3), (1.49, 3), (1.5, 1), (2.49, 1), (2.5, 0)]),
    ("earnings_growth_pct", "eps_growth_score", [(NAN, 3), (41, 10), (40, 8), (26, 8), (25, 6), (16, 6), (15, 4), (9, 4),
                                                 (8, 2), (1, 2), (0, 0), (-5, 0)]),
    ("revenue_growth_pct", "rev_growth_score", [(NAN, 3), (31, 10), (30, 8), (21, 8), (20, 6), (13, 6), (12, 4), (7, 4),
                                                (6, 2), (1, 2), (0, 0), (-4, 0)]),
    ("current_ratio", "curr_ratio_score", [(NAN, 2), (4.0, 5), (4.01, 0), (2.0, 5), (1.99, 4), (1.5, 4), (1.49, 3), (1.2, 3),
                                           (1.19, 2), (1.0, 2), (0.99, 0)]),
    ("dividend_yield_pct", "dividend_score", [(NAN, 0), (-1, 0), (0, 0), (0.5, 1), (1, 2), (1.99, 2), (2, 3), (3, 4),
                                              (4.99, 4), (5, 5), (9, 5)]),
    ("beta", "beta_score", [(NAN, 2), (0.6, 5), (1.2, 5), (0.59, 4), (0.4, 4), (0.39, 1), (1.21, 3), (1.5, 3), (1.51, 2),
                            (2.0, 2), (2.01, 1), (-1, 1)]),
]


@pytest.mark.parametrize("column,out_col,cases", COMPONENTS, ids=[c[1] for c in COMPONENTS])
def test_pegu_component_scores(column, out_col, cases):
    vals = [v for v, _ in cases]
    out = ds.calculate_pegu_scores(base_df(**{column: vals}))
    assert out[out_col].tolist() == [e for _, e in cases], list(zip(vals, out[out_col]))


def test_forward_pe_score_uses_ratio_of_forward_eps_to_pe():
    cases = [(10, 6.4, 5), (10, 6.5, 4), (10, 7.9, 4), (10, 8.0, 3), (10, 9.4, 3), (10, 9.5, 2), (10, 9.9, 2),
             (10, 10, 0), (10, 12, 0), (0, 5, 2), (-1, 5, 2), (NAN, 5, 2), (10, NAN, 2)]
    out = ds.calculate_pegu_scores(base_df(pe_ratio=[c[0] for c in cases], eps_forward=[c[1] for c in cases]))
    assert out["forward_pe_score"].tolist() == [c[2] for c in cases]


def test_pegu_total_and_grade_hand_computed():
    perfect = base_df(pe_ratio=[10], peg_ratio=[0.4], pb_ratio=[0.8], roe_pct=[30], operating_margins_pct=[20],
                      debt_equity=[0], earnings_growth_pct=[30], revenue_growth_pct=[15], eps_forward=[5],
                      current_ratio=[3.0], dividend_yield_pct=[3.5], beta=[0.9])
    out = ds.calculate_pegu_scores(perfect).iloc[0]
    # valuation 9+10+10, quality 9+6+10, growth 8+6+5, safety 5+4+5
    assert (out["valuation_score"], out["quality_score"], out["growth_score"], out["safety_score"]) == (29, 25, 19, 14)
    assert out["pegu_score"] == 87 and out["pegu_grade"] == "A+"


def test_pegu_all_missing_is_neutral_not_best():
    out = ds.calculate_pegu_scores(base_df(pe_ratio=[NAN])).iloc[0]
    # 3+4+3 | 3+3+4 | 3+3+2 | 2+0+2
    assert out["pegu_score"] == 32 and out["pegu_grade"] == "D"


GRADE_ROWS = [
    (80, "A+", {'pe_ratio': 10, 'peg_ratio': 0.8, 'pb_ratio': 0.8, 'roe_pct': 40, 'operating_margins_pct': 30, 'debt_equity': 0.2, 'earnings_growth_pct': 20, 'revenue_growth_pct': 35, 'eps_forward': 12, 'current_ratio': None, 'dividend_yield_pct': 4, 'beta': 0.9}),
    (79, "A", {'pe_ratio': 5, 'peg_ratio': 0.3, 'pb_ratio': 2.5, 'roe_pct': 30, 'operating_margins_pct': 40, 'debt_equity': 0, 'earnings_growth_pct': 30, 'revenue_growth_pct': 8, 'eps_forward': 3, 'current_ratio': 1.7, 'dividend_yield_pct': 1.5, 'beta': 3}),
    (70, "A", {'pe_ratio': 10, 'peg_ratio': 0.8, 'pb_ratio': 0.8, 'roe_pct': 40, 'operating_margins_pct': 30, 'debt_equity': 5, 'earnings_growth_pct': None, 'revenue_growth_pct': 15, 'eps_forward': 6, 'current_ratio': 1.7, 'dividend_yield_pct': 2.5, 'beta': 0.5}),
    (69, "B+", {'pe_ratio': 10, 'peg_ratio': 0.8, 'pb_ratio': 0.8, 'roe_pct': 30, 'operating_margins_pct': 30, 'debt_equity': None, 'earnings_growth_pct': 12, 'revenue_growth_pct': 35, 'eps_forward': 9, 'current_ratio': 5, 'dividend_yield_pct': 2.5, 'beta': 3}),
    (60, "B+", {'pe_ratio': 5, 'peg_ratio': 1.2, 'pb_ratio': 2.5, 'roe_pct': 30, 'operating_margins_pct': None, 'debt_equity': 0.4, 'earnings_growth_pct': None, 'revenue_growth_pct': 35, 'eps_forward': None, 'current_ratio': 5, 'dividend_yield_pct': 4, 'beta': 0.3}),
    (59, "B", {'pe_ratio': 40, 'peg_ratio': 0.3, 'pb_ratio': 4, 'roe_pct': 30, 'operating_margins_pct': 30, 'debt_equity': 0.2, 'earnings_growth_pct': -3, 'revenue_growth_pct': 25, 'eps_forward': 6, 'current_ratio': 0.5, 'dividend_yield_pct': 4, 'beta': None}),
    (50, "B", {'pe_ratio': 5, 'peg_ratio': 1.8, 'pb_ratio': 20, 'roe_pct': 18, 'operating_margins_pct': 2, 'debt_equity': 0.2, 'earnings_growth_pct': 30, 'revenue_growth_pct': 15, 'eps_forward': 6, 'current_ratio': 1.3, 'dividend_yield_pct': 4, 'beta': 1.4}),
    (49, "C", {'pe_ratio': 25, 'peg_ratio': 0.8, 'pb_ratio': 1.5, 'roe_pct': 30, 'operating_margins_pct': 2, 'debt_equity': 1.2, 'earnings_growth_pct': 20, 'revenue_growth_pct': -3, 'eps_forward': 9, 'current_ratio': 1.7, 'dividend_yield_pct': 0.5, 'beta': 3}),
    (40, "C", {'pe_ratio': 60, 'peg_ratio': 0.8, 'pb_ratio': 8, 'roe_pct': 5, 'operating_margins_pct': 15, 'debt_equity': 1.2, 'earnings_growth_pct': 12, 'revenue_growth_pct': 15, 'eps_forward': None, 'current_ratio': 1.7, 'dividend_yield_pct': 6, 'beta': 0.3}),
    (39, "D", {'pe_ratio': 40, 'peg_ratio': 1.8, 'pb_ratio': 0.8, 'roe_pct': 12, 'operating_margins_pct': None, 'debt_equity': 0.4, 'earnings_growth_pct': 12, 'revenue_growth_pct': 3, 'eps_forward': 12, 'current_ratio': 5, 'dividend_yield_pct': 0.5, 'beta': 3}),
    (25, "D", {'pe_ratio': None, 'peg_ratio': 1.8, 'pb_ratio': 8, 'roe_pct': 12, 'operating_margins_pct': -2, 'debt_equity': None, 'earnings_growth_pct': 5, 'revenue_growth_pct': 3, 'eps_forward': 8, 'current_ratio': 1.3, 'dividend_yield_pct': 0.5, 'beta': 3}),
    (24, "F", {'pe_ratio': 60, 'peg_ratio': 1.2, 'pb_ratio': 8, 'roe_pct': 5, 'operating_margins_pct': None, 'debt_equity': 2, 'earnings_growth_pct': 20, 'revenue_growth_pct': -3, 'eps_forward': None, 'current_ratio': 1.1, 'dividend_yield_pct': 0.5, 'beta': 3}),
]


@pytest.mark.parametrize("total,grade,row", GRADE_ROWS, ids=[f"{t}-{g}" for t, g, _ in GRADE_ROWS])
def test_pegu_grade_boundaries(total, grade, row):
    clean = {k: (np.nan if v is None else v) for k, v in row.items()}
    out = ds.calculate_pegu_scores(pd.DataFrame([clean])).iloc[0]
    assert (out["pegu_score"], out["pegu_grade"]) == (total, grade)


def test_pegu_percentile_ranks_within_batch():
    df = base_df(pe_ratio=[5, 40, 100], roe_pct=[40, 20, -5])
    out = ds.calculate_pegu_scores(df)
    assert out["pegu_percentile"].tolist() == sorted(out["pegu_percentile"].tolist(), reverse=True)
    assert out["pegu_percentile"].max() == 100.0
    assert "pegu_score" not in df.columns                                   # input untouched


# ---- Sarvas ------------------------------------------------------------------------------------

def sdf(**over):
    base = {"last_price": 100.0, "ma_50": np.nan, "ma_200": np.nan, "rsi_14": np.nan, "macd": np.nan,
            "volume_ratio": np.nan, "w52_high": np.nan, "eps_trailing": np.nan, "earnings_growth_pct": np.nan,
            "revenue_growth_pct": np.nan, "pe_ratio": np.nan, "debt_equity": np.nan, "roe_pct": np.nan,
            "upside_pct": np.nan, "pegu_score": 40.0}
    base.update(over)
    return pd.DataFrame([base])


# factor -> (override, points); every override is independent of the others
S_FACTORS = {
    "above50": ({"ma_50": 90.0}, 10), "above200": ({"ma_200": 90.0}, 10), "rsi": ({"rsi_14": 50.0}, 7),
    "macd": ({"macd": 0.5}, 5), "vol": ({"volume_ratio": 2.0}, 3), "near52": ({"w52_high": 100.0}, 2),
    "eps": ({"eps_trailing": 1.0}, 8), "eg": ({"earnings_growth_pct": 20.0}, 7), "rg": ({"revenue_growth_pct": 10.0}, 6),
    "pe": ({"pe_ratio": 20.0}, 5), "debt": ({"debt_equity": 0.5}, 5), "roe": ({"roe_pct": 20.0}, 5),
    "upside": ({"upside_pct": 20.0}, 4),
}


@pytest.mark.parametrize("name", list(S_FACTORS))
def test_sarvas_each_factor_alone(name):
    over, pts = S_FACTORS[name]
    assert ds.run_sarvas_scan(sdf(**over)).iloc[0]["sarvas_score"] == pts


def test_sarvas_golden_cross_alone_and_pegu_points():
    out = ds.run_sarvas_scan(sdf(ma_50=130.0, ma_200=120.0)).iloc[0]
    assert out["sarvas_score"] == 8 and bool(out["golden_cross"]) and not bool(out["above_50dma"])
    assert ds.run_sarvas_scan(sdf(ma_50=120.0, ma_200=130.0)).iloc[0]["sarvas_score"] == 0
    # Pegu contributes int((pegu - 40) * 15 / 60), clipped to 0..15
    for pegu, pts in ((0, 0), (39, 0), (40, 0), (43.9, 0), (44, 1), (60, 5), (80, 10), (100, 15), (250, 15)):
        assert ds.run_sarvas_scan(sdf(pegu_score=float(pegu))).iloc[0]["sarvas_score"] == pts, pegu


def test_sarvas_factor_boundaries():
    s = lambda **o: ds.run_sarvas_scan(sdf(**o)).iloc[0]["sarvas_score"]  # noqa: E731
    assert s(rsi_14=35) == 7 and s(rsi_14=68) == 7 and s(rsi_14=34.9) == 0 and s(rsi_14=68.1) == 0
    assert s(volume_ratio=1.5) == 0 and s(volume_ratio=1.51) == 3
    assert s(w52_high=125.0) == 2 and s(w52_high=125.1) == 0                      # price / high >= 0.80
    assert s(eps_trailing=0) == 0 and s(eps_trailing=0.01) == 8
    assert s(earnings_growth_pct=10) == 0 and s(revenue_growth_pct=8) == 0
    assert s(pe_ratio=0) == 0 and s(pe_ratio=35) == 0 and s(pe_ratio=34.9) == 5 and s(pe_ratio=0.1) == 5
    assert s(debt_equity=1.0) == 0 and s(debt_equity=0.99) == 5
    assert s(roe_pct=15) == 0 and s(upside_pct=10) == 0 and s(macd=0) == 0
    assert s(last_price=100.0, ma_50=100.0) == 0                                 # not strictly above


def test_sarvas_missing_technicals_do_not_count():
    out = ds.run_sarvas_scan(sdf()).iloc[0]
    for c in ("above_50dma", "above_200dma", "golden_cross", "rsi_neutral", "rsi_oversold", "macd_bullish", "vol_surge", "near_52w_high"):
        assert out[c] is None or pd.isna(out[c])
    assert out["rsi_oversold"] is None or pd.isna(out["rsi_oversold"])
    assert ds.run_sarvas_scan(sdf(rsi_14=20.0)).iloc[0]["rsi_oversold"] in (True, np.True_)


def build_for(points):
    """Smallest flag set (in a fixed order) leaving <= 15 points, which Pegu then fills exactly."""
    order = ["above50", "above200", "rsi", "eps", "eg", "rg", "pe", "debt", "roe", "macd", "upside", "vol", "near52"]
    remaining, over = points, {}
    for name in order:
        o, p = S_FACTORS[name]
        if remaining > 15 and p <= remaining:
            over.update(o)
            remaining -= p
    assert 0 <= remaining <= 15
    over["pegu_score"] = 40.0 + 4 * remaining
    return over


@pytest.mark.parametrize("pts,signal", [(100, "STRONG BUY"), (80, "STRONG BUY"), (79, "BUY"), (65, "BUY"), (64, "ACCUMULATE"),
                                       (50, "ACCUMULATE"), (49, "HOLD"), (35, "HOLD"), (34, "REDUCE"), (20, "REDUCE"),
                                       (19, "SELL"), (0, "SELL")])
def test_sarvas_signal_thresholds(pts, signal):
    out = ds.run_sarvas_scan(sdf(**build_for(min(pts, 92)))).iloc[0]
    assert out["sarvas_score"] == min(pts, 92)
    assert out["sarvas_signal"] == signal


def test_sarvas_score_is_clipped_to_100():
    over = {}
    for o, _ in S_FACTORS.values():
        over.update(o)
    over.update({"ma_50": 90.0, "ma_200": 80.0, "pegu_score": 100.0})
    assert ds.run_sarvas_scan(sdf(**over)).iloc[0]["sarvas_score"] <= 100


def test_sarvas_pass_requires_every_condition():
    ok = dict(ma_50=90.0, ma_200=80.0, rsi_14=50.0, pegu_score=60.0, eps_trailing=1.0, pe_ratio=20.0)
    assert bool(ds.run_sarvas_scan(sdf(**ok)).iloc[0]["sarvas_pass"]) is True
    for key, bad in (("ma_50", 110.0), ("ma_200", 110.0), ("rsi_14", 70.0), ("pegu_score", 59.9),
                     ("eps_trailing", 0.0), ("pe_ratio", 40.0)):
        assert bool(ds.run_sarvas_scan(sdf(**dict(ok, **{key: bad}))).iloc[0]["sarvas_pass"]) is False, key


def test_sarvas_does_not_mutate_input():
    df = sdf()
    ds.run_sarvas_scan(df)
    assert "sarvas_score" not in df.columns


# ---- workbook ----------------------------------------------------------------------------------

def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["daily_scan_excel", *argv])
    ds.main()


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory):
    """One full --mock run (building the workbook is the slow part); shared by the read-only checks below."""
    import io
    import contextlib
    work = tmp_path_factory.mktemp("daily_run")
    old_cwd, old_argv = os.getcwd(), sys.argv
    os.chdir(work)
    sys.argv = ["daily_scan_excel", "--mock", "--top-n", "7", "--data-dir", str(work / "d"), "--out-dir", str(work / "o")]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ds.main()
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv
    import openpyxl
    path = next((work / "o").glob("NSE_BSE_Daily_Scan_*.xlsx"))
    return types.SimpleNamespace(work=work, path=path, out=buf.getvalue(), wb=openpyxl.load_workbook(path))


def test_main_mock_end_to_end(mock_run):
    names = mock_run.wb.sheetnames
    assert len(names) == 10
    expected = ["Summary", "All Stocks (Pegu)", "Sarvas Pass", "Top 7 Picks", "NSE", "BSE",
                "Sector Analysis", "Score Breakdown", "Benchmark", "Scan Info"]
    assert all(n.endswith(e) for n, e in zip(names, expected)), names
    out = mock_run.out
    assert "[1/4] Skipping extractor pre-run" in out and "[4/4] Saved" in out and "Sheets: 10" in out
    assert "TOP 10 PICKS (by Pegu + Sarvas)" in out
    assert (mock_run.work / "d").is_dir()                      # data dir is created even in mock mode


def test_all_stocks_sheet_has_one_row_per_unique_stock(mock_run):
    df = ds.load_or_generate_data(str(mock_run.work / "d"), True).drop_duplicates(subset=["symbol", "exchange"])
    all_sheet = mock_run.wb["All Stocks (Pegu)"]
    data_rows = [r for r in all_sheet.iter_rows(min_row=1, values_only=True) if r and r[0] == "RELIANCE"]
    assert len(data_rows) == 1
    symbols = {r[0] for r in all_sheet.iter_rows(values_only=True) if r and isinstance(r[0], str)}
    assert set(df["symbol"]) <= symbols
    assert "Stocks scored  : %s" % f"{len(df):,}" in mock_run.out


def test_exchange_sheets_split_by_exchange(mock_run):
    df = ds.load_or_generate_data(str(mock_run.work / "d"), True).drop_duplicates(subset=["symbol", "exchange"])
    nse = mock_run.wb[[n for n in mock_run.wb.sheetnames if n.endswith(" NSE")][0]]
    bse = mock_run.wb[[n for n in mock_run.wb.sheetnames if n.endswith(" BSE")][0]]
    nse_syms = {r[0] for r in nse.iter_rows(values_only=True)} & set(df["symbol"])
    bse_syms = {r[0] for r in bse.iter_rows(values_only=True)} & set(df["symbol"])
    assert "RELIANCE" in nse_syms and "RELIANCE" not in bse_syms
    assert "500325" in bse_syms and "500325" not in nse_syms


def test_top_picks_sheet_respects_top_n(mock_run):
    ws = mock_run.wb[[n for n in mock_run.wb.sheetnames if "Picks" in n][0]]
    ranks = [r[0] for r in ws.iter_rows(values_only=True) if isinstance(r[0], int)]
    assert ranks == [1, 2, 3, 4, 5, 6, 7]


def test_scan_info_sheet_counts(mock_run):
    ws = mock_run.wb[mock_run.wb.sheetnames[-1]]
    info = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(3, 25)}
    df = ds.load_or_generate_data(str(mock_run.work / "d"), True).drop_duplicates(subset=["symbol", "exchange"])
    assert info["Total Stocks"] == len(df)
    assert info["NSE Stocks"] == int((df.exchange == "NSE").sum())
    assert info["BSE Stocks"] == int((df.exchange == "BSE").sum())
    assert info["Sectors Covered"] == df["sector"].nunique()
    assert info["Signal levels"].startswith("STRONG BUY≥80")


def test_benchmark_sheet_placeholder_without_csv(mock_run):
    ws = mock_run.wb[[n for n in mock_run.wb.sheetnames if "Benchmark" in n][0]]
    assert ws["A3"].value == "Run nse_bse_benchmark.py to generate timing data."


def test_benchmark_sheet_reads_csv_when_present(tmp_path, monkeypatch):
    import openpyxl
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    pd.DataFrame({"section": ["import", "parse", "math"], "approach": ["pure", "pure", "numpy"],
                  "value": [0.5, 12.0, 3.0]}).to_csv(tmp_path / "reports" / "benchmark_results.csv", index=False)
    wb = openpyxl.Workbook()
    ds.write_benchmark_sheet(wb)
    ws = wb[wb.sheetnames[-1]]
    assert [ws.cell(r, 4).value for r in (4, 5, 6)] == ["seconds", "\u00b5s", "ms"]
    assert [ws.cell(r, 3).value for r in (4, 5, 6)] == [0.5, 12.0, 3.0]
    assert [ws.cell(r, 2).value for r in (4, 5, 6)] == ["pure", "pure", "numpy"]


def test_main_extractor_prerun_unless_mock_or_no_fetch(tmp_path, monkeypatch, capsys):
    import openpyxl
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(ds.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=3))
    real = ds.load_or_generate_data
    monkeypatch.setattr(ds, "load_or_generate_data", lambda d, m: real(d, True))
    for fn in [f for f in dir(ds) if f.startswith("write_") and f.endswith("_sheet")]:
        monkeypatch.setattr(ds, fn, lambda *a, **k: None)
    monkeypatch.setattr(openpyxl.Workbook, "save", lambda self, path: open(path, "wb").close())
    base = ["--data-dir", str(tmp_path / "d"), "--out-dir", str(tmp_path / "o")]
    run_main(monkeypatch, "--index", "NIFTY50", *base)
    assert len(calls) == 1
    assert calls[0][1:] == ["nse_bse_extractor.py", "--exchange", "BOTH", "--index", "NIFTY50", "--batch-size", "50",
                            "--delay", "0.3", "--output-dir", str(tmp_path / "d")]
    assert "Extractor exited 3" in capsys.readouterr().out
    run_main(monkeypatch, "--no-fetch", *base)
    run_main(monkeypatch, "--mock", *base)
    assert len(calls) == 1


# ---- boundary cases added after the mutation check ------------------------------------------------

def test_extractor_csv_with_exactly_six_prices_is_used(tmp_path, monkeypatch):
    pd.DataFrame({"symbol": list("ABCDEF"), "exchange": ["NSE"] * 6, "last_price": [1.0] * 6}).to_csv(
        tmp_path / "all_stocks_combined.csv", index=False)
    monkeypatch.setattr(ds, "fetch_live_nse_data", lambda s: pytest.fail("extractor CSV should be used"))
    assert len(ds.load_or_generate_data(str(tmp_path), use_mock=False)) == 6


def test_enrich_with_exactly_fifty_bars_computes_ma50(monkeypatch):
    closes = [100.0 + i for i in range(50)]
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf({}, closes))
    r = ds.enrich_with_yfinance(pd.DataFrame({"symbol": ["A"], "exchange": ["NSE"]})).iloc[0]
    assert r["ma_50"] == pytest.approx(np.mean(closes))
