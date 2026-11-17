"""Pegu (0-100) and Sarvas scores in global_scanner.py, hand-computed.

The breakpoint helper _score(val, [(threshold, score), ...]) returns the score of
the first threshold the value is below. A missing value must not earn points it
has not shown: these tests prove a blank row used to grade 'A'."""
import pytest

import global_scanner as gs

FULL = {
    "pe_ratio": 12, "peg_ratio": 0.8, "pb_ratio": 1.5,                 # 8 + 10 + 10 = 28
    "roe": 18, "operating_margins": 12, "debt_to_equity": 30,          # 18 + 8 + 10 -> cap 30
    "earnings_growth": 12, "revenue_growth": 8,                        # 12 + 5
    "last_price": 100, "eps_forward": 8,                               # fwd PE 12.5 -> 6  => 23
    "current_ratio": 1.8, "dividend_yield": 2.5, "beta": 0.9,          # 7 + 5 + 3 = 15
}


def test_score_breakpoints():
    bp = [(0, 0), (10, 4), (15, 8), (1e9, 0)]
    assert gs._score(-1, bp) == 0
    assert gs._score(9.99, bp) == 4
    assert gs._score(10, bp) == 8          # threshold is exclusive
    assert gs._score(2e9, bp) == 0         # beyond the last breakpoint


def test_pegu_full_row_hand_computed():
    assert gs.pegu_score(FULL) == (96.0, "A+")


def test_pegu_grade_bands():
    weak = dict(FULL, pe_ratio=60, peg_ratio=4, pb_ratio=12)          # valuation 0 -> 68
    assert gs.pegu_score(weak) == (68.0, "B+")


def test_missing_roe_scores_no_better_than_a_known_low_roe():
    """Prove-it: _score() returned the LAST bucket for None, and the last ROE bucket
    is the maximum 30 points, so a stock with no ROE outranked one with ROE 4%."""
    base = dict(FULL, operating_margins=2, debt_to_equity=100)        # opm 2, de 4
    known_low = gs.pegu_score(dict(base, roe=4))[0]                   # roe 3 -> quality 9
    missing = gs.pegu_score(dict(base, roe=None))[0]
    assert missing <= known_low


def test_missing_current_ratio_scores_no_better_than_a_known_weak_one():
    base = dict(FULL, dividend_yield=0.5, beta=2.0)                   # div 2, beta 0
    known_weak = gs.pegu_score(dict(base, current_ratio=0.8))[0]      # cr 4
    missing = gs.pegu_score(dict(base, current_ratio=float("nan")))[0]
    assert missing <= known_weak


def test_blank_row_is_not_an_A_grade():
    total, grade = gs.pegu_score({})
    assert grade == "F", (total, grade)


def test_sarvas_hand_computed():
    row = {"last_price": 100, "ma50": 95, "ma200": 90, "rsi_14": 55, "macd": 1.2,
           "volume_ratio": 2.0, "week52_high": 105,                   # 8+10+10+7+5+5+7 = 52
           "eps_trailing": 5, "earnings_growth": 12, "revenue_growth": 6,
           "pe_ratio": 20, "debt_to_equity": 30, "roe": 18,
           "target_price": 120}                                       # 10+8+8+7+7+7+8 = 55
    assert gs.sarvas_signal(row, pegu=60) == (112, "STRONG BUY")      # +5 Pegu bonus
    assert gs.sarvas_signal({}, pegu=0) == (0, "SELL")
    assert gs.sarvas_signal({"last_price": 10, "eps_trailing": 1, "roe": 20,
                             "debt_to_equity": 10}, pegu=0) == (24, "REDUCE")
