# ML002 data feasibility preregistration · 2026-10-26

**Status at registration: NOT_RUN. Data-only feasibility, no new trading candidate.**

Purpose: determine whether an already-mentioned three-exposure ETF pool can be
used for an independently specified *future* cross-sectional learning experiment.
This does not authorize training or evaluate performance. Keep frozen failed
ML001 and all original H002/H003/AG1/CA1 records intact.

## Fixed universe, horizon and provenance

- Shanghai 510300: broad-equity ETF; 511010: sovereign-bond ETF; 518880:
  physical-gold tracking ETF. This pool was previously examined in CA1 and is
  **SEEN_DEVELOPMENT**, not a project-untouched holdout, however cleanly the
  source comparison might finish. 2019-01-01 through 2025-12-31 only.
- Independent SSE official dayk nominal daily OHLC versus Tencent year-scoped
  `day` OHLC, exact Decimal cells, zero tolerance. SSE provides OHLC authority,
  but an API-wide point-in-time/unadjusted contract is NOT certified. Check
  symbol-specific response IDs and every session against the index calendar
  proxy; reject omissions/extra dates and any mismatches. No manual patch,
  stale fallback, close-to-open substitution, source vote or profit-based
  selection. The earlier DQ001 reviewed precedence is not automatically
  extended beyond its 20 cells.
- Record exact URL, SHA-256 and byte size of *every* successful HTTP response;
  publish only bounded aggregate comparisons and limited mismatch coordinates,
  never raw daily data. Source access is not a redistribution license. No retry,
  cookies, access-control bypass, secrets or extra paid vendor.
- Quantify whether Leek's **existing research assumptions** (50,000 yuan,
  20% initial entry budget, 100-unit research lot) can purchase even one lot
  at each observed open, **before commission/slippage**. This is a feasibility
  warning, not a verified broker minimum or an authorization to increase size.
  No budget/lot adjustments permitted in this data-only stage.

## Mandatory blockers regardless of clean OHLC

A full three-asset panel is NOT trainable until point-in-time constituents,
ETF-specific record/ex/pay cash distributions and other share actions,
calendar/tradability and unit/tick conventions, and a jointly funded,
risk-matched benchmark have all been fixed and independently verified. The
511010 instrument has nontrivial cash distributions: official SSE announcement
on 2025-09-18 records 2025-09-22 registration, 2025-09-23 ex date and
2025-09-26 payment, 14.50 yuan per 10 units. Ignoring distributions can create
false return/label signals.

## Report and decision boundary

`PRICE_FEASIBILITY_ONLY_CA_BLOCKED` means **prices only** pass all three
symbol/calendar checks; `BLOCKED_PRICE_PANEL` / `BLOCKED_SOURCE_ACCESS_OR_SCHEMA`
mean research cannot proceed on the proposed data. Neither is an investment
screen or permission to train. Output always sets trainable=false,
new_models=0, historical_trade_runs=0, automatic_promotion=false.
Failures retained. Do not silently swap an ETF, shift dates to delete conflicts,
search parameters or declare three independent exposure successes. A future
ML002 *strategy* needs its own pre-result hypothesis, cost/risk-matched
benchmarks, timestamped features/labels and candidate-budget accounting.

## Source pointers / licensing notes

- Official SSE 511010 instrument: https://www.sse.com.cn/disclosure/announcement/general/jjzssgg/c/c_20240926_10762410.shtml
- Official SSE 518880 instrument: https://www.sse.com.cn/disclosure/announcement/general/jjzssgg/c/c_20251204_10800738.shtml
- Official 511010 cash distribution: https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-09-18/511010_20250918_FU3S.pdf
- Qlib study-workflow interfaces: https://qlib.readthedocs.io/en/stable/component/workflow.html (documentation ideas only; no runtime or source copied). Qlib is MIT licensed.
- Existing Leek and prior ML001 source-adjudication patterns are MIT repository code. This probe uses Python stdlib; no 3rd-party code imported.
