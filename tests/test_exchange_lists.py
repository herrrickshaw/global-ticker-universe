"""Hermetic tests for fetch_exchange_lists parsers (no network)."""
import fetch_exchange_lists as fx


def test_parse_tpex_qualifies_exchange_and_filters_codes():
    rows = [
        {"SecuritiesCompanyCode": "1240", "CompanyAbbreviation": "A", "DateOfListing": "20180808"},
        {"SecuritiesCompanyCode": "1240", "CompanyAbbreviation": "dup"},
        {"SecuritiesCompanyCode": "03001P", "CompanyAbbreviation": "not ordinary"},
        {"SecuritiesCompanyCode": "", "CompanyAbbreviation": "blank"},
    ]
    out = fx.parse_tpex(rows)
    assert [r["yf_ticker"] for r in out] == ["1240.TWO"]
    assert out[0]["exchange"] == "TPEX"


def test_parse_sgx_keeps_only_investable_types():
    payload = {"data": {"prices": [
        {"nc": "D05", "n": "DBS", "type": "stocks", "m": "MAINBOARD"},
        {"nc": "O5RU", "n": "AIMS", "type": "reits", "m": "MAINBOARD"},
        {"nc": "W1", "n": "warrant", "type": "structuredwarrants"},
        {"nc": None, "n": "x", "type": "stocks"},
        {"nc": "D05", "n": "dup", "type": "stocks"},
    ]}}
    out = fx.parse_sgx(payload)
    assert [r["yf_ticker"] for r in out] == ["D05.SI", "O5RU.SI"]
    assert all(r["exchange"] == "SGX" for r in out)
