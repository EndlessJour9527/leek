# leek

Paper-only quantitative research primitives and an offline synthetic replay.
This is a small stdlib-only accounting and data-contract foundation, not a trading system or a
claim of investment performance. No market data, account information, broker
adapter, credentials, network calls, or third-party framework code is included.

## Run offline

Python 3.10+ from the checkout root; no package installation is required:

```sh
python -m unittest discover -s tests -v
python -m examples.paper_demo
```

If pytest is already installed, `python -m pytest` runs the same suite. The tests
and demo are fully synthetic and require no downloads or service accounts.
GitHub Actions bootstraps Python through official actions; the actual test run
is offline and has no data/feed dependency. The demo prints a synthetic NAV of
1998.00, not a measured or forecast return.

## Module boundaries

- `leek.ledger`: shared spendable cash, Decimal quantities/cost basis, synthetic
  fills, settlement lots, record/ex/pay corporate-action phases, receivables,
  explicit raw-price valuation. Slippage is already in the fill price and is
  reported separately, never deducted a second time.
- `leek.ca_math`: exact-ratio price-basis and total-return transformations. Share
  rounding in an account is deliberately separate from return-series math.
- `leek.risk_signals`: fixed-pool equal-weight returns from supplied positive
  total-return levels; 60 returns (61 levels), sample variance, annualization
  factor 252, 10% target volatility, 95% exposure cap. These are explicit research
  defaults, not universally suitable trading parameters. The current-close
  signal is for a later execution opportunity, never that same close.
- `leek.contract`: fail-closed calendar, fixed-universe qualifications, raw OHLC
  validation and input SHA-256 checks; no forward fill or inferred qualification.
- `leek.interfaces`: a data-only `SignalProvider` protocol and immutable
  `SignalEnvelope`. `validate(decision_time)` enforces asof <= available_at <=
  decision_time, timezone-aware timestamps, a dataset digest and a long-only
  target weight. It neither allocates a portfolio nor executes an order.
- `schemas`: version-1 wire contracts. Numeric market/account quantities use
  decimal strings. Schema shape checks do not replace semantic Python checks.

Use decimal strings at boundaries. Core arithmetic follows the caller's Decimal
context (default precision 28); importing the package does not mutate it. Risk
volatility uses double-precision floats and is not exact Decimal accounting.

## Explicit model limitations

The ledger assumes one currency, long-only positions, no borrowing, and no tax
calculation. A buy lot is sellable only on a strictly later ISO date. This is a
simplified T+1 date rule, not a venue settlement/calendar engine. Callers must
supply the exchange session calendar, chronological event ordering, valid
settlement rules, fees, lot constraints, price limits and already-approved fills.
No missing calendar or corporate-action evidence should be silently inferred.

Call `record` after the entitlement snapshot, `ex` once on the correct basis
transition, and `pay` once when cash becomes spendable. A sale after record date
does not erase that cash entitlement. Splits transform the held quantity and its
lots while preserving aggregate cost basis. Supported rounding policies are
`exact` and `ceil_whole_account`; neither is a default claim about an exchange.
Unsupported events (rights, spin-offs, cash-in-lieu, withholding, FX, etc.) need
separate specifications and tests. Receivables contribute to NAV but cannot fund
purchases. Valuation needs a raw close for every nonzero position; never send an
adjusted price to the fill or valuation interface.

The ledger itself is an in-memory research component. The synthetic replay below
adds an immutable report and checkpoint, but neither component has production
release qualification or a real-trading safety case.
Do not mutate ledger internals directly. Provider timestamps and input hashes
must be established by an independently trusted ingestion layer; this package
cannot prove that a provider's claimed availability time is true.

## Test coverage

Synthetic tests cover shared cash, fees/slippage once, settled partial lots,
dividend receivables, duplicate corporate actions/payments, reverse splits and
account rounding, cost-basis preservation, randomized cash/lot invariants,
fail-closed prices/calendars/hashes, signal warmup, variance hand calculations,
future-path independence, and signal availability timestamps.

The suite does not establish historical profitability, validate a real data
vendor, or replace a full execution simulator. It exercises only the modules
included here; real historical data ingestion, portfolio strategy selection, and
research batch orchestration are outside scope.

## Future framework adapters

Keep external research engines behind `SignalProvider` and normalize their
outputs into `SignalEnvelope`; core accounting remains independently testable.
A future Qlib adapter can supply research signals without importing a broker
stack. Any adapter must preserve raw-vs-adjusted price provenance, time of data
availability and dataset hashes. No external framework is bundled or required.
Review the exact version and its license before adding a dependency or copying
code. Do not treat a framework backtest NAV as this ledger's accounting result.

## Provenance and licensing

This contribution extracts and hardens standalone accounting/CA/data-contract
ideas and synthetic tests from an existing research prototype. It does not copy
third-party implementation code or redistribute market datasets, reports, or
source documents. Python's standard library is the only runtime dependency;
pytest is an optional separately installed test runner. CI references the
upstream GitHub checkout and setup-python actions, without vendoring them.

The project uses the [MIT License](LICENSE) supplied by the maintainers. This
contribution preserves that license unchanged. Check the exact version and
license of any future third-party dependency; the repository's MIT license does
not relicense external code or market data.


## Deterministic synthetic replay (second increment)

`leek.replay` connects strict input validation, one causal signal, next-session
open-price model fills, the existing Decimal ledger, and daily JSON reporting.
It is deliberately **one synthetic instrument, one SIM currency, long-only,
fixed whole-share quantity**. It does not migrate an existing historical engine,
run the separate 60-return volatility strategy, or enable live/paper brokerage.

Run from the checkout root, using new output directories each time:

```sh
python -m leek.replay --config examples/fixtures/replay-config.json \
  --input examples/fixtures/replay-bars.json --output /tmp/leek-full
python -m leek.replay --config examples/fixtures/replay-config.json \
  --input examples/fixtures/replay-bars.json --output /tmp/leek-part --stop-after 3
python -m leek.replay --config examples/fixtures/replay-config.json \
  --input examples/fixtures/replay-bars.json --output /tmp/leek-resumed \
  --resume /tmp/leek-part/checkpoint.json
cmp /tmp/leek-full/report.json /tmp/leek-resumed/report.json
```

### Contract and event order

- Input and configuration require exact fields, version `synthetic-replay.v1`,
  finite bounded decimal strings, and unique JSON keys. The fixtures are the
  complete wire-format examples. Unknown fields are rejected, including extra
  adjustment or corporate-action fields on bars.
- The calendar is an explicit, sorted unique list of session dates. Exactly one
  matching OHLC bar is required for every session, in the same order. There is
  no inferred weekday/holiday calendar, forward fill, or skipped missing bar.
  It does not establish that supplied synthetic dates match any exchange.
  The fixture intentionally skips a weekday to exercise calendar-based timing.
- `synthetic` must be true, `currency` must be `SIM`, `adjustment` must be `raw`,
  and `corporate_actions` must be an empty list. Any corporate action is rejected
  before creating output. The ledger's standalone CA helpers are **not** wired
  into this replay; do not remove or hide events to make real data pass.
- At close t, the signal compares close[t] to close[t-lookback]. Strictly greater
  selects the configured quantity; otherwise the target is zero. No signal
  exists during warmup. Quantity delta is fixed at t, never sized from a future
  open, high, low or close. Signal availability is modeled at 23:59:59 UTC on t.
- A nonzero delta is attempted at the *next listed session's open*. Execution
  reads that open only. Daily high/low are validation constraints, never fill
  or order inputs. Daily close then values holdings and forms the next signal.
  The last signal may remain pending with `execute_on: null`; it is never filled
  at the terminal close or on an invented extra session. `complete` means all
  input sessions were consumed, not that the last pending signal was executed.
- Every attempt has a deterministic instrument/signal-date/side event ID.
  Buys/sells get adverse `slippage_bps`, plus the configured flat commission
  per filled order. Insufficient cash rejects the whole order without fees or
  partial fills. All modeled fees are commission and embedded slippage; taxes,
  spread beyond that slippage, impact, liquidity, volume, lot-size rules, venue
  price limits, currencies and corporate actions are unsupported. These fills
  are unconstrained research proxies, never claims about executable prices.

### Reports, recovery, and safety boundaries

`report.json` contains signals, every filled/rejected execution attempt, pending
order, processed event IDs, and each session's cash, quantity, cost basis, market
value, NAV, realized/unrealized/total P&L, cumulative commission and slippage.
Slippage is reported separately but embedded once in price. The included full
fixture ends at synthetic NAV `9933.920`, with commission `3` and slippage
`3.080`; these are test arithmetic, not investment results.

`checkpoint.json` binds the processed prefix to the exact input/configuration
bytes (SHA-256), all package Python source files, model/version and Decimal
precision. The replay isolates arithmetic in a fixed 64-digit, half-even Decimal
context. Formatting-only input changes also invalidate recovery.

Checkpointing occurs at a successful requested stop (`--stop-after N`, an
absolute session count) or at completion, not continuously during each session.
Resume replays the saved prefix from the bound inputs and compares every report
field and digest before proceeding. It never imports untrusted cash/position
state, and needs the original entire input bundle. This O(N) replay-prefix
verification favors reviewability over fast restoration of large histories;
reports/checkpoints hold the entire prefix in memory. Hashes detect changes,
not malicious authorship; they are not signatures or data-vendor certification.

Every invocation requires a **new output directory**, including resume and
repeat resume. Existing directories and files are never overwritten. Completed
file bytes are fsynced and published with an atomic exclusive hard link on a
local filesystem supporting hard links. Concurrent publication cannot clobber
a winner. This is file-level atomicity, not a transactional multi-file database
or a portable power-loss durability guarantee. A crash before checkpoint
publication requires rerunning from an earlier checkpoint or from the start;
a crash after checkpoint publication but before report publication can recover
to a new output directory. Never repair a checkpoint by editing its cursor.

The same inputs/source/config yield byte-identical full and resumed reports and
checkpoints; outputs contain no runtime timestamp or machine path. Repeating a
resume into another new directory replays the same virtual history, with one
execution per event inside each report. There is no global exactly-once broker
transaction claim and no external side effect to duplicate.

### Synthetic multi-asset shared-cash replay

An additive `python -m leek.portfolio_replay` CLI demonstrates multiple synthetic
instruments sharing one Ledger cash balance. It fixes sell-before-buy allocation
and explicit symbol priority, preserves next-session causal fills, reports
rejections/costs/per-symbol NAV contributions and floating P&L, and verifies
byte-identical checkpoint recovery. See the [versioned contract and runnable
example](docs/synthetic-portfolio-replay-v1.md). This is synthetic-only framework
infrastructure, not historical strategy validation or live trading support.

### Cash-dividend-aware synthetic portfolio replay

An additive `python -m leek.cash_dividend_replay` entry point connects the
existing Ledger's record/ex/pay phases to multi-instrument synthetic replay.
It separates gross income, unpaid receivables and spendable cash, uses causal
forward total-return signals, and verifies every phase on checkpoint recovery.
Only exact cash dividends are supported; splits, tax, complex actions and real
data are explicitly rejected. The old replay entry points are unchanged.
See the [contract, limitations and runnable fixtures](docs/synthetic-cash-dividend-replay-v1.md).
This is accounting infrastructure, not a profitable strategy or live-trading qualification.
