# Global Ticker Universe

A curated, exchange-qualified list of listed equities across 25+ markets (60,971 validated tickers), plus the
Python tools that build it (`universe_builder.py`), load it (`global_tickers.py`) and run a Pegu + Sarvas
scoring scan over it (`global_scanner.py`, `daily_scan_excel.py`). Outputs are JSON/CSV ticker files in `data/`
and, for the scanners, per-market CSVs and an Excel workbook in `reports/`.

> Status: maintained. Ticker lists were cross-referenced against FinanceDatabase (July 2026 snapshot);
> educational use only, not investment advice.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/global-ticker-universe/blob/main/notebooks/colab_test.ipynb)
See also [How to use this repo with an AI assistant](HOW_TO_USE_WITH_AI.md).

## What it does
- Stores one validated ticker list: [`data/validated_universe_flat.csv`](data/validated_universe_flat.csv) (60,971 rows: market, exchange, yfinance symbol).
- Builds `data/global_universe.json` and `data/global_universe_flat.csv` from per-market source files plus static fallback lists (`python universe_builder.py`).
- Serves symbols to other code: `tickers_for("US", "IN")`, `all_tickers()`, `market_codes()` (`global_tickers.py`).
- Scores stocks with the Pegu score (valuation, quality, growth, safety; 0-100, grade A+..F) and the Sarvas signal (STRONG BUY..SELL) via yfinance (`global_scanner.py`).
- Writes a daily NSE/BSE Excel report from the same scoring ideas (`daily_scan_excel.py`).

## Quick start
```bash
git clone https://github.com/herrrickshaw/global-ticker-universe.git
cd global-ticker-universe
python -m venv .venv && source .venv/bin/activate
pip install pandas numpy openpyxl yfinance      # no requirements.txt yet; yfinance only for live scans
python -c "import global_tickers as g; print(g.market_codes()[:5], len(g.tickers_for('IN')))"
```
Rebuild the universe files: `python universe_builder.py`. Scan without network: `python global_scanner.py --mock --markets IN`.

## How it works
Ticker symbols always carry an explicit exchange qualifier (`.NS`, `.T`, `.L`, ...). The suffix comes from the
`MARKETS` allowlist in `universe_builder.py` or from the source file's own `yf_ticker` field; it is never
guessed from the shape of a ticker.

| Stage | Module | Output |
|---|---|---|
| Load per-market sources (`_UNIVERSE_SOURCES` registry: JSON/CSV file, else static fallback list) | `universe_builder.py` | in-memory dict per market |
| Merge Europe file + static `MARKETS` entries | `universe_builder.build_universe` | `data/global_universe.json`, `data/global_universe_flat.csv` |
| Lazy read of the universe | `global_tickers.py` | symbol lists |
| Fetch prices and fundamentals (batched yfinance) | `global_scanner.fetch_batch` / `compute_technicals` | per-symbol dicts |
| Pure scoring (`pegu_score`, `sarvas_signal`) | `scoring.py` | score, grade, signal |
| Per-market scan with checkpoints | `global_scanner.scan_universe` | `reports/global_scan_YYYYMMDD/<MKT>_scan.csv` |
| NSE/BSE daily workbook | `daily_scan_excel.py` | `reports/NSE_BSE_Daily_Scan_YYYYMMDD.xlsx` |

Adding a market to the builder means adding one `_Market(...)` entry to `_UNIVERSE_SOURCES`.

## Repository layout
| Path | Purpose |
|---|---|
| `universe_builder.py` | builds the universe from `data/` files and static lists |
| `global_tickers.py` | lightweight loader/accessors for `data/global_universe.json` |
| `scoring.py` | pure Pegu/Sarvas scoring functions (no I/O) |
| `global_scanner.py` | batched yfinance scan, checkpoints, Excel export (CLI) |
| `daily_scan_excel.py` | NSE/BSE daily Excel report (CLI; `--mock` uses built-in sample stocks) |
| `tests/` | pytest suite incl. characterisation tests with golden fixtures in `tests/fixtures/` |
| `data/` | tracked ticker files (per-market `*_tickers_full.json`, `india_tickers_full.csv`, flat CSVs) |
| `notebooks/colab_test.ipynb` | Colab smoke test |

## Data sources
| Source | What is taken | Access route | Licence / caveat |
|---|---|---|---|
| [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) | exchange listings used for validation and most `*_tickers_full.json` | downloaded CSVs | check upstream licence before redistributing |
| NSE / BSE, ASX, HKEX, TWSE, B3, JSE, Tadawul and others | official listings behind the per-market files (see `source` fields in `data/global_universe.json`) | downloaded files | check each exchange's terms |
| Eurex T7 GraphQL (Deutsche Boerse) | German derivatives universe, PEGU tables | lives in the sibling research repo | see below |

## Configuration
No environment variables or secrets. `universe_builder.DATA` and `global_tickers._DATA` point at `data/` next to the code.

## Testing
```bash
pip install -r requirements-dev.txt
pytest -q          # 122 tests; no network
ruff check .
```

## Limitations and known issues
- Per-market counts: Germany 17,121; Austria 8,813; US 6,443; China 3,431; India 2,984; Brazil 2,755; UK 2,713; Japan 2,658; Italy 2,249; France 2,050; Australia 1,657; Hong Kong 1,473; Sweden 1,146; Norway 1,004; Canada 779; Taiwan 664; Denmark 643; South Korea 545; Argentina 442; South Africa 391; Russia 242; Saudi Arabia 154; New Zealand 137; Switzerland 132; Spain 106 (July 2026 snapshot).
- `us/jp/kr/sg/europe_tickers_full.json` are not tracked in this repo, so rebuilding here uses the static fallback lists for those markets and gives fewer tickers (about 60,395) than the validated CSV.
- `global_scanner.load_universe` imports `MARKETS` from `global_tickers`, which does not define it; the import error is swallowed, so the "International" block is skipped. Fixing it would change scan output and is left for a follow-up.
- The Eurex / PEGU result tables formerly in this README are produced in the research repo `global-market-research-platform` (branch `claude/nse-bse-pegu-scoring-k7vu9`); their data files are not in this repo.
- The Pegu/Sarvas scores are heuristic screens, not validated trading signals.

## Related repositories
- [global-market-research-platform](https://github.com/herrrickshaw/global-market-research-platform) - Eurex GraphQL client, German/India PEGU scoring, universe validation (`validate_universe_fd.py`).

## Licence
No licence file yet - all rights reserved.
