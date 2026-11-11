
```markdown
# DATA_SOURCES.md - global-ticker-universe

Last reviewed 2026-11-08. This repo is a list of Yahoo-style tickers (symbol + suffix), names and a few attributes. It is not an ISIN master and not a list of domestic issuers. Terms marked UNVERIFIED were not read from the publisher.

## How the universe is built
`universe_builder.py` merges per-market JSON lists into `data/global_universe.json` / `global_universe_flat.csv` (75,815 tickers, 34 market codes). `validated_universe_flat.csv` (60,971) is the subset cross-referenced with FinanceDatabase on 2026-07-27. Exchange is taken from the list a code came from (never inferred from ticker shape). Additions on 2026-10-17: TPEX (`.TWO`, 893) and SGX (`.SI`, 721 rows) via `fetch_exchange_lists.py`.

## Sources
| Dataset | Publisher / URL | Terms | Fields kept | Coverage (rows) | Refresh | Caveats |
|---|---|---|---|---|---|---|
| FinanceDatabase equities | J. Bouma, https://github.com/JerBouma/FinanceDatabase | MIT (c) 2023 Jeroen Bouma | yf_ticker, name, exchange, sector, market_cap bucket | UK 2,713; FR 2,050; IT 2,249; DE 17,121; AT 8,813; NO 1,004; SE 1,146; DK 643; AR 442; ZA 391; SA 371; RU 242; NZ 137; ... | snapshot 2026-07-27 | upstream values come from Yahoo-type aggregators; includes foreign cross-listings (UK 1,096 `0xxx.L`; DE `.F` 16,080; AT `.VI` all) |
| TPEX listed companies | Taipei Exchange OpenAPI https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O | Taiwan Open Government Data License v1.0, attribution (https://data.gov.tw/license) | yf_ticker (`.TWO`), name, exchange, listed date | 893 | 2026-10-17 | endpoint truncates; retry loop |
| TWSE list | TWSE official | UNVERIFIED (likely Taiwan OGDL) | yf_ticker, name | 1,065 | 2026-07-27 | - |
| SGX securities | https://api.sgx.com/securities/v1.1 (public endpoint behind sgx.com) | No published reuse licence | yf_ticker (`.SI`), name, board, type | 721 | 2026-10-17 | stocks/REITs/trusts/ETFs only; warrants, certificates, ADRs excluded |
| ASX official directory | https://www.asx.com.au/asx/research/ASXListedCompanies.csv | UNVERIFIED | asx_code, name, sector, listing_date, market_cap | 2,297 | 2026-07 | market_cap/listing_date should be dropped from public copy |
| HKEX ListOfSecurities | HKEX | UNVERIFIED | code, name, category, sub_category | 2,701 | Jun 2025 | oldest list |
| SSE / SZSE | exchange sites | UNVERIFIED | code, name, type | 2,513 + 2,832 | 2026-07 | - |
| B3 instruments | B3 | UNVERIFIED | code, name | 2,755 | Nov 2024 | - |
| JPX / KRX / US lists | JPX, KRX (KOSPI/KOSDAQ), Nasdaq Trader + rreichel3 US-Stock-Symbols | UNVERIFIED; rreichel3 repo has no LICENSE at /main/LICENSE | yf_ticker, name | JP 3,618; KR 2,606; US 7,726 (global file) | source files not committed | cannot be rebuilt from this repo |
| JSE list | hand-curated | n/a | yf_ticker, name, sector, market_cap | 391 | 2026-07 | provenance of sector/market_cap unknown |
| India scan snapshot | own scan on Yahoo prices | Yahoo terms apply to price fields | Symbol, Suffix, LTP, Darvas box, Piotroski, Coffee Can | 5,981 (271 symbols twice) | 2026-07-27 | price columns should not be published |

## What is not in this repo
ISIN, CUSIP, SEDOL, FIGI, LEI; GICS/MSCI/FTSE classifications; index constituents; PEGU score files and Eurex product tables referenced in README (they live in a private repository).

## Known issues
README counts (25 markets) vs data (34); mislabelled country sizes (DE, AT, UK, FR); Russia `.ME` likely stale since 2022; duplicate listings of one issuer under several suffixes; README links to a private repo.

## Attribution to include
FinanceDatabase (MIT); Taipei Exchange via Taiwan Open Government Data License v1.0; SGX, ASX, HKEX, SSE/SZSE, B3, JPX, KRX, Nasdaq for symbol lists (UNVERIFIED terms).
```
