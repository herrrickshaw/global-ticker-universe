"""
fetch_exchange_lists.py
=======================
Pulls official, open exchange listing files and writes them in the same
shape as the other data/*_tickers_full.json files
([{"yf_ticker", "name", "exchange", ...}]).

Sources (verified by curl 2026-10-17, no API key):
  - TPEX (Taipei Exchange, OTC board)  -> data/tpex_tickers_full.json
      https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O
      Taiwan Government Open Data licence (https://data.gov.tw/license), attribution required.
  - SGX (Singapore Exchange securities list) -> data/sgx_tickers_full.json
      https://api.sgx.com/securities/v1.1  (public endpoint behind sgx.com's price pages;
      no published reuse licence -- ticker codes/names only, see README caveat)

Exchange qualification comes from WHICH exchange's list a code was read from
(.TWO because it is on the TPEX list, .SI because it is on the SGX list) --
never from the shape of the ticker.

Usage:
    python3 fetch_exchange_lists.py              # fetch both, write data/*.json
    python3 fetch_exchange_lists.py --dry-run    # fetch + report, write nothing
"""
from __future__ import annotations
import argparse, json, re, time, urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
SGX_URL = "https://api.sgx.com/securities/v1.1?excludetypes=bonds&params=nc,n,type,m,cur"
# SGX instrument types treated as investable listed securities (no warrants/certificates/ADRs).
SGX_TYPES = {"stocks", "reits", "businesstrusts", "etfs"}


def _get_json(url: str, tries: int = 8):
    """TPEX's endpoint intermittently resets/truncates; retry until the body parses."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            body = urllib.request.urlopen(req, timeout=60).read()
            return json.loads(body.decode("utf-8"))
        except Exception as e:  # truncated JSON, reset, timeout
            last = e
            time.sleep(2)
    raise RuntimeError(f"{url} failed after {tries} tries: {last}")


def parse_tpex(rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        code = (r.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code) or code in seen:
            continue  # ordinary-share company codes only
        seen.add(code)
        out.append({
            "yf_ticker": f"{code}.TWO",
            "name": (r.get("CompanyAbbreviation") or r.get("CompanyName") or "").strip(),
            "exchange": "TPEX",
            "listed": (r.get("DateOfListing") or "").strip(),
        })
    return out


def parse_sgx(payload: dict) -> list[dict]:
    out, seen = [], set()
    for r in payload.get("data", {}).get("prices", []):
        code = (r.get("nc") or "").strip()
        if r.get("type") not in SGX_TYPES or not code or code in seen:
            continue
        seen.add(code)
        out.append({
            "yf_ticker": f"{code}.SI",
            "name": (r.get("n") or "").strip(),
            "exchange": "SGX",
            "board": r.get("m"),
            "type": r.get("type"),
        })
    return out


def _existing(code: str) -> set[str]:
    u = json.load(open(DATA / "global_universe.json"))
    return set(u.get(code, {}).get("yf_symbols", []))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    jobs = [("tpex", parse_tpex(_get_json(TPEX_URL)), "TW"),
            ("sgx", parse_sgx(_get_json(SGX_URL)), "SG")]
    for name, rows, mk in jobs:
        have = _existing(mk)
        new = [r for r in rows if r["yf_ticker"] not in have]
        print(f"{name}: {len(rows)} fetched, {len(new)} not already in {mk} universe")
        if not a.dry_run:
            with open(DATA / f"{name}_tickers_full.json", "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
