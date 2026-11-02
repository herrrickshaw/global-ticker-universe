"""
scoring.py
==========
Pure scoring functions shared by the global scanner: no I/O, no network.

  pegu_score(row)          -> (0-100 score, letter grade)     valuation/quality/growth/safety
  sarvas_signal(row, pegu) -> (0-100 score, signal label)     technical + fundamental points

``row`` is a flat dict of yfinance-derived fields (see global_scanner.fetch_batch).
"""

from __future__ import annotations

import math
from typing import Tuple

def _pct(v):
    """Normalise a ratio (0.21) or already-percent (21.0) value to percent, 2 dp; None passes through."""
    if v is None:
        return None
    return round(v * 100, 2) if abs(v) < 2 else round(v, 2)


# ── Pegu scoring ──────────────────────────────────────────────────────────────

def _score(val, breakpoints):
    """Step-score ``val`` against ascending (upper_bound, points) pairs; None/NaN gets the last points."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return breakpoints[-1][1]
    for threshold, score in breakpoints:
        if val < threshold:
            return score
    return breakpoints[-1][1]


def pegu_score(row: dict) -> Tuple[float, str]:
    """Compute Pegu score (0-100) and grade for a stock data dict."""

    # Valuation (30 pts)
    pe  = _score(row.get("pe_ratio"),  [(0,0),(10,4),(15,8),(20,12),(25,10),(35,6),(50,2),(1e9,0)])
    peg = _score(row.get("peg_ratio"), [(0,0),(0.5,6),(1.0,10),(1.5,8),(2.0,4),(3.0,2),(1e9,0)])
    pb  = _score(row.get("pb_ratio"),  [(0,0),(1,6),(2,10),(3,8),(5,4),(10,2),(1e9,0)])
    val = min(pe + peg + pb, 30)

    # Quality (30 pts)
    roe = _score(row.get("roe"),              [(0,0),(5,3),(10,7),(15,12),(20,18),(25,22),(30,25),(1e9,30)])
    opm = _score(row.get("operating_margins"),[(0,0),(5,2),(10,5),(15,8),(20,10),(25,12),(30,14),(1e9,16)])
    de  = row.get("debt_to_equity")
    de_s= 14 if de is None else (14 if de < 0 else _score(de, [(0,14),(20,12),(40,10),(80,7),(120,4),(200,2),(1e9,0)]))
    qual = min(roe + opm + de_s, 30)

    # Growth (25 pts)
    epsg = _score(row.get("earnings_growth"), [(-1e9,0),(0,1),(5,4),(10,8),(15,12),(20,16),(25,20),(30,24),(1e9,25)])
    revg = _score(row.get("revenue_growth"),  [(-1e9,0),(0,1),(5,2),(10,5),(15,7),(20,9),(25,11),(1e9,13)])
    efwd = row.get("eps_forward")
    fwd_pe = (row.get("last_price") / efwd) if efwd and efwd > 0 and row.get("last_price") else None
    fpe_s  = _score(fwd_pe, [(0,0),(10,4),(15,6),(20,5),(25,4),(35,2),(1e9,0)])
    grw = min(epsg + revg + fpe_s, 25)

    # Safety (15 pts)
    cr  = _score(row.get("current_ratio"),  [(0,0),(0.5,0),(1.0,4),(1.5,7),(2.0,10),(3.0,12),(1e9,15)])
    div = _score(row.get("dividend_yield"), [(0,0),(1,2),(2,4),(3,5),(4,5),(6,4),(1e9,3)])
    beta= row.get("beta")
    b_s = 5 if beta is None else _score(abs(beta), [(0,0),(0.5,5),(0.8,4),(1.0,3),(1.2,2),(1.5,1),(1e9,0)])
    saf = min(cr + div + b_s, 15)

    total = val + qual + grw + saf
    if   total >= 80: grade = "A+"
    elif total >= 70: grade = "A"
    elif total >= 60: grade = "B+"
    elif total >= 50: grade = "B"
    elif total >= 40: grade = "C"
    elif total >= 25: grade = "D"
    else:             grade = "F"

    return round(total, 1), grade


def sarvas_signal(row: dict, pegu: float) -> Tuple[int, str]:
    """Return (score, signal) for Sarvas scan."""
    pts = 0

    # Technical (45 pts)
    ltp    = row.get("last_price", 0) or 0
    ma50   = row.get("ma50") or 0
    ma200  = row.get("ma200") or 0
    rsi    = row.get("rsi_14")
    macd   = row.get("macd")
    vr     = row.get("volume_ratio")
    h52    = row.get("week52_high") or 0

    if ma50  and ltp > ma50:             pts += 8
    if ma200 and ltp > ma200:            pts += 10
    if ma50  and ma200 and ma50 > ma200: pts += 10  # golden cross
    if rsi   and 35 <= rsi <= 68:        pts += 7
    if macd  and macd > 0:               pts += 5
    if vr    and vr > 1.5:              pts += 5
    if h52   and ltp >= 0.9 * h52:      pts += 7

    # Fundamental (55 pts)
    eps = row.get("eps_trailing")
    eg  = row.get("earnings_growth")
    rg  = row.get("revenue_growth")
    pe  = row.get("pe_ratio")
    de  = row.get("debt_to_equity")
    roe = row.get("roe")
    tp  = row.get("target_price")

    if eps and eps > 0:                  pts += 10
    if eg  and eg > 10:                  pts += 8
    if rg  and rg > 5:                   pts += 8
    if pe  and 5 < pe < 30:             pts += 7
    if de  is not None and de < 50:      pts += 7
    if roe and roe > 15:                 pts += 7
    if tp  and ltp and tp > ltp * 1.1:  pts += 8
    if pegu >= 60:                       pts += 5  # Pegu bonus

    if   pts >= 80: sig = "STRONG BUY"
    elif pts >= 65: sig = "BUY"
    elif pts >= 50: sig = "ACCUMULATE"
    elif pts >= 35: sig = "HOLD"
    elif pts >= 20: sig = "REDUCE"
    else:           sig = "SELL"

    return pts, sig
