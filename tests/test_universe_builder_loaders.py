"""universe_builder: per-market loaders, build_universe and save_universe (data dir redirected to tmp_path)."""
import csv
import json

import pytest

import universe_builder as ub


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(ub, "DATA", tmp_path)
    return tmp_path


def write_json(data, name, rows):
    (data / name).write_text(json.dumps(rows), encoding="utf-8")


# (loader, data file, static fallback list name or None, fallback suffix)
SIMPLE = [
    ("_load_jp", "jp_tickers_full.json", "JP_TICKERS", ".T"),
    ("_load_kr", "kr_tickers_full.json", "KR_TICKERS", ".KS"),
    ("_load_au", "au_tickers_full.json", "AU_TICKERS", ".AX"),
    ("_load_sg", "sg_tickers_full.json", "SG_TICKERS", ".SI"),
    ("_load_cn_sse", "cn_sse_tickers_full.json", "CN_SS_TICKERS", ".SS"),
    ("_load_cn_sz", "cn_sz_tickers_full.json", "CN_SZ_TICKERS", ".SZ"),
    ("_load_hk", "hk_tickers_full.json", "HK_TICKERS", ".HK"),
    ("_load_tw", "tw_tickers_full.json", "TW_TICKERS", ".TW"),
    ("_load_ca", "ca_tickers_full.json", "CA_TICKERS", ".TO"),
    ("_load_br", "br_tickers_full.json", "BR_TICKERS", ".SA"),
    ("_load_uk", "uk_tickers_full.json", "UK_TICKERS", ".L"),
    ("_load_sa", "sa_tickers_full.json", "SA_TICKERS", ".SR"),
    ("_load_it", "it_tickers_full.json", "IT_TICKERS", ".MI"),
    ("_load_de", "de_tickers_full.json", "DE_TICKERS", ".DE"),
    ("_load_fr", "fr_tickers_full.json", "FR_TICKERS", ".PA"),
    ("_load_za", "za_tickers_full.json", None, None),
    ("_load_se", "se_tickers_full.json", None, None),
    ("_load_no", "no_tickers_full.json", None, None),
    ("_load_dk", "dk_tickers_full.json", None, None),
    ("_load_at", "at_tickers_full.json", None, None),
    ("_load_nz", "nz_tickers_full.json", None, None),
    ("_load_ar", "ar_tickers_full.json", None, None),
    ("_load_ru", "ru_tickers_full.json", None, None),
]
IDS = [s[0] for s in SIMPLE]


@pytest.mark.parametrize("fn,fname,static,sfx", SIMPLE, ids=IDS)
def test_loader_reads_file_in_order_and_dedupes(data, fn, fname, static, sfx):
    write_json(data, fname, [{"yf_ticker": "B.X"}, {"yf_ticker": "A.X"}, {"yf_ticker": "B.X"}, {"yf_ticker": "C.X"}])
    assert getattr(ub, fn)() == ["B.X", "A.X", "C.X"]


@pytest.mark.parametrize("fn,fname,static,sfx", SIMPLE, ids=IDS)
def test_loader_without_file_falls_back(data, fn, fname, static, sfx):
    got = getattr(ub, fn)()
    if static is None:
        assert got == []
    else:
        assert got == [f"{t}{sfx}" for t in getattr(ub, static)]
        assert got and all(s.endswith(sfx) for s in got)


@pytest.mark.parametrize("fn,fname,static,sfx", SIMPLE, ids=IDS)
def test_loader_empty_file_returns_empty_not_fallback(data, fn, fname, static, sfx):
    write_json(data, fname, [])
    assert getattr(ub, fn)() == []


def test_loader_reads_utf8_names(data):
    write_json(data, "jp_tickers_full.json", [{"yf_ticker": "7203.T", "name": "トヨタ"}])
    assert ub._load_jp() == ["7203.T"]


def test_load_india(data):
    with open(data / "india_tickers_full.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Symbol", "Suffix", "LTP"])
        w.writerows([["TCS", ".NS", 1], ["TCS", ".NS", 2], ["TCS", ".BO", 3], [" INFY ", " .NS ", 4],
                     ["", ".NS", 5], ["500325", ".BO", 6]])
    assert ub._load_india() == ["TCS.NS", "TCS.BO", "INFY.NS", "500325.BO"]


def test_load_india_default_suffix_and_missing_file(data):
    assert ub._load_india() == []
    (data / "india_tickers_full.csv").write_text("Symbol\nTCS\n")
    assert ub._load_india() == ["TCS.NS"]


def test_load_us(data):
    assert len(ub._load_us()) == 30 and ub._load_us()[0] == "AAPL"
    (data / "us_tickers_full.json").write_text(json.dumps({"MSFT": {}, "AAPL": {}, "BRK-B": {}}))
    assert ub._load_us() == ["AAPL", "BRK-B", "MSFT"]               # sorted keys


def test_load_europe_csv(data):
    assert ub._load_europe_csv() == {}
    write_json(data, "europe_tickers_full.json", [
        {"market_code": "SE", "yf_ticker": "VOLV-B.ST"}, {"market_code": "SE", "yf_ticker": "ERIC-B.ST"},
        {"market_code": "FI", "yf_ticker": "NOKIA.HE"}, {"market_code": "", "yf_ticker": "X.Y"},
        {"market_code": "NO", "yf_ticker": ""}, {"yf_ticker": "Z.Z"}])
    assert ub._load_europe_csv() == {"SE": ["VOLV-B.ST", "ERIC-B.ST"], "FI": ["NOKIA.HE"]}


def test_dedup_keeps_first_and_handles_unhashable_free_input():
    assert ub._dedup(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
    assert ub._dedup(iter(["x", "x"])) == ["x"]


# ---- build / save ----------------------------------------------------------------------

def test_build_universe_fallback_only(data, capsys):
    u = ub.build_universe()
    assert u["IN"]["count"] == 0 and u["IN"]["yf_symbols"] == []
    assert u["US"]["count"] == 30
    assert u["JP"]["yf_symbols"][0] == f"{ub.JP_TICKERS[0]}.T"
    cn = u["CN"]["yf_symbols"]
    assert len(cn) == len(set(cn)) and any(s.endswith(".SS") for s in cn) and any(s.endswith(".SZ") for s in cn)
    for code in ("ZA", "SE", "NO", "DK", "AT", "NZ", "AR", "RU", "GR", "FI"):   # empty loaders are skipped
        assert code not in u
    for code in ("CH", "NL", "ES", "AE"):
        assert code in u and u[code]["source"] == "static + europe_tickers_full.json"
    assert all(v["count"] == len(v["yf_symbols"]) for v in u.values())
    assert "  US  :     30" in capsys.readouterr().out


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="the static fallback loaders (e.g. _load_jp: [f'{t}.T' for t in JP_TICKERS]) skip _dedup, "
                          "so with no data files JP/SG/HK/TW/CA/UK/IT/DE/FR contain repeated symbols and an "
                          "inflated count (JP 200 vs 180 unique)")
def test_build_universe_fallback_has_no_duplicate_symbols(data):
    for code, meta in ub.build_universe().items():
        assert len(meta["yf_symbols"]) == len(set(meta["yf_symbols"])), code


def test_build_universe_entry_shape(data):
    for code, meta in ub.build_universe().items():
        assert set(meta) == {"name", "exchange", "yf_symbols", "count", "source"}, code


def test_build_universe_uses_data_files_and_merges_europe(data):
    write_json(data, "za_tickers_full.json", [{"yf_ticker": "NPN.JO"}])
    write_json(data, "se_tickers_full.json", [{"yf_ticker": "VOLV-B.ST"}])
    write_json(data, "cn_sse_tickers_full.json", [{"yf_ticker": "600519.SS"}])
    write_json(data, "cn_sz_tickers_full.json", [{"yf_ticker": "000001.SZ"}, {"yf_ticker": "600519.SS"}])
    write_json(data, "europe_tickers_full.json", [
        {"market_code": "ES", "yf_ticker": "NEWCO.MC"},
        {"market_code": "ES", "yf_ticker": f"{ub.MARKETS['ES']['tickers'][0]}{ub.MARKETS['ES']['suffix']}"},
        {"market_code": "FI", "yf_ticker": "NOKIA.HE"},
        {"market_code": "FI", "yf_ticker": "NOKIA.HE"},
        {"market_code": "SE", "yf_ticker": "SHOULD-NOT-DUP.ST"},
        {"market_code": "PL", "yf_ticker": "PKN.WA"},
    ])
    u = ub.build_universe()
    assert u["ZA"]["yf_symbols"] == ["NPN.JO"] and u["ZA"]["count"] == 1
    assert u["SE"]["yf_symbols"] == ["VOLV-B.ST"]                        # dedicated file wins, not re-added as NEW
    assert u["CN"]["yf_symbols"] == ["600519.SS", "000001.SZ"]           # SSE + SZSE merged without duplicates
    es = u["ES"]["yf_symbols"]
    assert es.count(f"{ub.MARKETS['ES']['tickers'][0]}.MC") == 1 and "NEWCO.MC" in es and es[-1] == "NEWCO.MC"
    assert u["FI"] == {"name": "Finland", "exchange": "Nasdaq Helsinki", "yf_symbols": ["NOKIA.HE"], "count": 1,
                       "source": "europe_tickers_full.json"}
    assert u["PL"]["yf_symbols"] == ["PKN.WA"]
    assert "GR" not in u                                                # no data -> no empty market


def test_build_universe_prints_new_marker(data, capsys):
    write_json(data, "europe_tickers_full.json", [{"market_code": "BE", "yf_ticker": "SOLB.BR"}])
    ub.build_universe()
    assert "  BE  :      1  (NEW)" in capsys.readouterr().out


def test_build_universe_extra_suffix_markets(data):
    meta = {"name": "X", "exchange": "XX", "suffix": ".AA", "tickers": ["A", "A", "B"],
            "extra": {"suffix": ".BB", "tickers": ["C", "C"]}}
    ub.MARKETS["ZZ"] = meta
    try:
        got = ub.build_universe()["ZZ"]["yf_symbols"]
    finally:
        del ub.MARKETS["ZZ"]
    # base tickers are de-duplicated before suffixing; extras too; the merged list is de-duplicated again
    assert got == ["A.AA", "B.AA", "C.BB"]


def test_save_universe_writes_json_and_flat_csv(data, capsys):
    universe = {
        "US": {"name": "United States", "exchange": "NYSE", "yf_symbols": ["AAPL", "MSFT"], "count": 2},
        "IN": {"name": "India", "exchange": "NSE/BSE", "yf_symbols": ["TCS.NS"], "count": 1},
    }
    ub.save_universe(universe)
    assert json.loads((data / "global_universe.json").read_text()) == universe
    with open(data / "global_universe_flat.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["market_code", "market_name", "exchange", "yf_symbol"]
    assert rows[1:] == [["US", "United States", "NYSE", "AAPL"], ["US", "United States", "NYSE", "MSFT"],
                        ["IN", "India", "NSE/BSE", "TCS.NS"]]
    out = capsys.readouterr().out
    assert "(3 rows)" in out and "Grand total: 3 tickers across 2 markets" in out


@pytest.mark.parametrize("code,fname,name,exchange", [
    ("ZA", "za_tickers_full.json", "South Africa", None), ("SE", "se_tickers_full.json", "Sweden", "Nasdaq Stockholm"),
    ("NO", "no_tickers_full.json", "Norway", "Oslo Bors"), ("DK", "dk_tickers_full.json", "Denmark", "Nasdaq Copenhagen"),
    ("AT", "at_tickers_full.json", "Austria", "Vienna Stock Exchange"), ("NZ", "nz_tickers_full.json", "New Zealand", "NZX"),
    ("AR", "ar_tickers_full.json", "Argentina", "Bolsa de Buenos Aires"), ("RU", "ru_tickers_full.json", "Russia", "MOEX"),
])
def test_build_universe_optional_market_from_its_own_file(data, code, fname, name, exchange):
    write_json(data, fname, [{"yf_ticker": f"{code}1.X"}, {"yf_ticker": f"{code}1.X"}, {"yf_ticker": f"{code}2.X"}])
    meta = ub.build_universe()[code]
    assert meta["yf_symbols"] == [f"{code}1.X", f"{code}2.X"] and meta["count"] == 2
    assert meta["name"] == name
    if exchange:
        assert meta["exchange"] == exchange
    assert fname in meta["source"]
