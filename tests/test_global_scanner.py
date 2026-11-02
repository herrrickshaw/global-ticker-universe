"""Characterisation tests for global_scanner + scoring.

Golden values in fixtures/scanner_golden.json were captured from the pre-refactor
implementation (commit 6bcdbe5). yfinance is replaced by an in-memory fake: no network.
"""
import json
import math
import types
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

import global_scanner as gs  # noqa: E402
import scoring  # noqa: E402

GOLD = json.loads((Path(__file__).parent / "fixtures" / "scanner_golden.json").read_text())


def _row(raw):
    return {k: (float("nan") if v == "NaN" else v) for k, v in raw.items()}


def _roundtrip(obj):
    return json.loads(json.dumps(obj, default=str))


@pytest.mark.parametrize("case", GOLD["rows"])
def test_pegu_and_sarvas_match_golden(case):
    row = _row(case["in"])
    pegu, grade = scoring.pegu_score(row)
    assert (pegu, grade) == (case["pegu"], case["grade"])
    assert scoring.sarvas_signal(row, pegu) == (case["sarvas"], case["signal"])


def test_global_scanner_reexports_scoring():
    assert gs.pegu_score is scoring.pegu_score
    assert gs.sarvas_signal is scoring.sarvas_signal


@pytest.mark.parametrize("value,expected", GOLD["pcts"])
def test_pct(value, expected):
    assert scoring._pct(value) == expected


def test_score_bands_and_missing():
    bands = [(0, 0), (10, 5), (1e9, 9)]
    assert scoring._score(5, bands) == 5
    assert scoring._score(None, bands) == 9
    assert scoring._score(float("nan"), bands) == 9
    assert not math.isnan(scoring._score(-1, bands))


# ── fake yfinance ─────────────────────────────────────────────────────────────

SYMS = ["AAA", "BBB", "SHORT"]


def _fake_frame():
    idx = pd.bdate_range("2025-01-01", periods=300)
    rng = np.random.RandomState(3)
    frames = {}
    for s in SYMS:
        c = 100 + np.cumsum(rng.randn(300))
        frames[s] = pd.DataFrame(
            {"Close": c, "Volume": rng.randint(1000, 5000, 300).astype(float)}, index=idx)
    frames["SHORT"] = frames["SHORT"].iloc[:10]
    big = pd.DataFrame(index=idx, columns=pd.MultiIndex.from_product([["Close", "Volume"], SYMS]), dtype=float)
    for s in SYMS:
        for f in ("Close", "Volume"):
            big[(f, s)] = frames[s][f].reindex(idx)
    return big


class _FakeTicker:
    def __init__(self, sym):
        self.sym = sym

    @property
    def info(self):
        if self.sym == "BBB":
            raise RuntimeError("boom")
        return {"trailingPE": 18.5, "returnOnEquity": 0.21, "operatingMargins": 0.15,
                "revenueGrowth": 0.08, "dividendYield": 2.5, "longName": "Aaa Corp",
                "sector": "Tech", "targetMeanPrice": 130.0, "debtToEquity": 40}


@pytest.fixture
def fake_yf(monkeypatch):
    big = _fake_frame()
    fake = types.SimpleNamespace(download=lambda *a, **k: big, Ticker=_FakeTicker)
    monkeypatch.setattr(gs, "yf", fake, raising=False)
    monkeypatch.setattr(gs, "_YF", True)
    return fake


def test_fetch_batch_matches_golden(fake_yf):
    assert _roundtrip(gs.fetch_batch(SYMS)) == GOLD["fetch_batch"]


def test_fetch_batch_empty_download(monkeypatch):
    fake = types.SimpleNamespace(download=lambda *a, **k: pd.DataFrame(), Ticker=_FakeTicker)
    monkeypatch.setattr(gs, "yf", fake, raising=False)
    monkeypatch.setattr(gs, "_YF", True)
    assert gs.fetch_batch(SYMS) == GOLD["fetch_empty"] == {}


def test_fetch_batch_without_yfinance(monkeypatch):
    monkeypatch.setattr(gs, "_YF", False)
    assert gs.fetch_batch(SYMS) == {}


def test_compute_technicals_short_series_still_computes():
    df = pd.DataFrame({"Close": np.linspace(10, 20, 60)})
    out = gs.compute_technicals(df)
    assert out["last_price"] == 20.0
    assert out["volume_ratio"] is None          # no Volume column
    assert out["week52_high"] == 20.0


def _universe_from_gold():
    rows = [_row(c["in"]) for c in GOLD["rows"][:3]]
    return pd.DataFrame([
        {"symbol": "X", "yf_symbol": "X.NS", "market": "IN", **rows[0]},
        {"symbol": "Y", "yf_symbol": "Y.NS", "market": "IN", **rows[1]},
        {"symbol": "Z", "yf_symbol": "Z", "market": "US", **rows[2]},
    ])


def test_scan_universe_mock_matches_golden(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPORTS", tmp_path)
    monkeypatch.setattr(gs, "TODAY", "2026-01-01")
    res = gs.scan_universe(_universe_from_gold(), mock=True)
    assert _roundtrip(json.loads(res.to_json(orient="records"))) == GOLD["scan_mock"]
    assert (tmp_path / next(p.name for p in tmp_path.iterdir()) / "IN_scan.csv").exists()


def test_scan_universe_live_matches_golden(tmp_path, monkeypatch, fake_yf):
    monkeypatch.setattr(gs, "REPORTS", tmp_path)
    monkeypatch.setattr(gs, "TODAY", "2026-01-01")
    uni = pd.DataFrame([{"symbol": s, "yf_symbol": s, "market": "US", "last_price": 100.0} for s in SYMS])
    res = gs.scan_universe(uni, mock=False, batch_size=2, workers=1)
    assert _roundtrip(json.loads(res.to_json(orient="records"))) == GOLD["scan_live"]
