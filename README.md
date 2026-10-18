# leek

Paper-only quantitative research primitives. This first increment is a small,
stdlib-only accounting and data-contract foundation, not a trading system or a
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

This is an in-memory research component, with no persistent audit journal,
reconciliation, production release qualification, or real-trading safety case.
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
included here; research batch runners and strategy selection are outside scope.

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
