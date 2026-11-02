"""Characterisation test: scoring pipeline on the built-in sample data (--mock path)."""
import hashlib
import tempfile

import pytest

pytest.importorskip("pandas")
pytest.importorskip("openpyxl")

import daily_scan_excel as d  # noqa: E402

# md5 of run_sarvas_scan(calculate_pegu_scores(...)).to_json(orient="records") captured pre-refactor
EXPECTED_ROWS = 84
EXPECTED_MD5 = "8e4b0d0a69ca216357211c02833d04f0"


def test_mock_pipeline_unchanged():
    import numpy as np
    import pandas as pd
    with tempfile.TemporaryDirectory() as t:
        df = d.load_or_generate_data(t, True)
    df = df.drop_duplicates(subset=["symbol", "exchange"]).reset_index(drop=True)
    for src, dst in [("roe", "roe_pct"), ("operating_margins", "operating_margins_pct"),
                     ("revenue_growth", "revenue_growth_pct"), ("earnings_growth", "earnings_growth_pct"),
                     ("dividend_yield", "dividend_yield_pct")]:
        if dst not in df.columns:
            df[dst] = df[src] * 100 if src in df.columns else float("nan")
    for col in ("upside_pct", "volume_ratio", "rsi_14", "macd"):
        if col not in df.columns:
            df[col] = np.nan
    final = d.run_sarvas_scan(d.calculate_pegu_scores(df))
    assert isinstance(final, pd.DataFrame) and len(final) == EXPECTED_ROWS
    assert hashlib.md5(final.to_json(orient="records").encode()).hexdigest() == EXPECTED_MD5


def test_safe_float():
    assert d._safe_float("1.5") == 1.5
    assert d._safe_float("x", default=-1) == -1
