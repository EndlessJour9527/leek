# Synthetic shared-cash portfolio replay v1

This additive engine is an offline orchestration example, not a historical
strategy validation or executable exchange simulator. It reuses `Ledger` and
the strict single-instrument validation, hashing and atomic-publication helpers.
`leek.replay`, Ledger, and the separate H001 diagnostics are not modified.

## Reproducible example

Run from the repository root with Python 3.10 or later; no dependencies, network,
account, broker, credentials or real market data are used.

```sh
python -m leek.portfolio_replay --config examples/fixtures/portfolio-config.json --input examples/fixtures/portfolio-bars.json --output /tmp/portfolio-full
python -m leek.portfolio_replay --config examples/fixtures/portfolio-config.json --input examples/fixtures/portfolio-bars.json --output /tmp/portfolio-part --stop-after 3
python -m leek.portfolio_replay --config examples/fixtures/portfolio-config.json --input examples/fixtures/portfolio-bars.json --output /tmp/portfolio-resumed --resume /tmp/portfolio-part/checkpoint.json
cmp /tmp/portfolio-full/report.json /tmp/portfolio-resumed/report.json
cmp /tmp/portfolio-full/checkpoint.json /tmp/portfolio-resumed/checkpoint.json
python -m unittest discover -s tests -v
```

All output directories must be new. Python API:
`leek.portfolio_replay.run(config_path, input_path, output_dir, resume=None,
stop_after=None)`. `stop_after` is an absolute session count, from 1 through
calendar length. The returned report is also written as canonical UTF-8 JSON.

## Frozen input contract

Every object has exactly the documented fields. Duplicate JSON keys, unknown
fields, nonfinite values and numeric JSON values for monetary amounts fail
closed. The executable validator is `leek.portfolio_replay.validate`.

Configuration fields:

- `version`: `synthetic-portfolio-replay.v1`
- `initial_cash`: strictly positive decimal string, shared by every instrument
- `quantities`: exact instrument-to-positive-whole-share-decimal-string mapping
- `commission`: nonnegative flat decimal-string fee per successful fill
- `slippage_bps`: nonnegative decimal string, strictly less than 10000
- `lookback`: integer 1–10000, never a boolean
- `symbol_priority`: explicit permutation of the entire fixed universe
- `execution_policy`: `sells-first.priority-order.all-or-reject.v1`

Dataset fields:

- `version`: `synthetic-portfolio-replay.v1`
- `synthetic`: literal `true`
- `instruments`: 2–64 distinct ASCII alphanumeric names of 1–32 characters
- `currency`: `SIM`
- `adjustment`: `raw`
- `corporate_actions`: exactly `[]`; this orchestration does not process actions
- `calendar`: nonempty, unique, ascending canonical ISO dates
- `bars`: exact instrument mapping to lists of `{date, open, high, low, close}`

Each symbol must have exactly one ordered raw OHLC bar for every calendar date,
including dates on which it has no holdings. All prices must be positive,
consistent OHLC decimal strings. Decimal strings are at most 40 characters,
values at most 1e12, and exponents between -12 and 12 inclusive. All input is
validated before creating state or any output, even for a partial run.
Suspensions, missing observations, unknown calendars, adjusted bars and company
actions cannot be silently filled, skipped or approximated. A declaration of
synthetic data is a caller contract, not a provenance certification.

## Causality and allocation policy

1. At each explicit session's open, execute intents fixed at the previous
   explicit session's close. Execution uses only the current raw open.
2. Process all sells first, then all buys. Within each side, use only
   `symbol_priority`. Neither dataset order nor prices choose the priority.
3. Sell proceeds after costs are spendable by later buys that same session.
   There is one common cash balance. Each intended quantity is filled in full
   or rejected; no resizing, borrowing, partial fill, pro-rata allocation or
   implicit cash reservation occurs. Allocation is sequential priority, not
   an equal-weight or portfolio-optimization strategy.
4. Adverse slippage is `open * (1 +/- bps/10000)`; one configured commission
   applies only to a successful fill. Rejection charges zero costs.
5. At the close, mark all positions and then independently compare each close
   with its own close `lookback` sessions earlier. Strictly greater means its
   fixed configured quantity; equal/lower means zero. Warmup produces no intent.
   A delta from current filled holdings creates a next-open intent. A rejected
   entry may produce a new intent at that session's close if still warranted.
6. Terminal close intents have `execute_on: null` and remain pending; there is
   no forced liquidation or fabricated terminal fill. `complete` means every
   input session was processed, not every intent filled.

Calendar dates model UTC close availability at `23:59:59+00:00`, not actual
exchange timestamps. Ledger's settlement rule is earlier acquisition *date*,
not a full clearing calendar. These limits are acceptable only for this
synthetic demonstration.

Stable rejection reasons are `INSUFFICIENT_CASH`,
`INSUFFICIENT_SETTLED_SHARES`, and `INSUFFICIENT_SELL_FEE_CASH`. Other Ledger
errors abort rather than being disguised as routine rejections. Settlement
rejection is defensive; normal fixed-position next-session intents settle
under this simplified model.

## Accounting and report semantics

Daily portfolio NAV = shared cash + sum of symbol marked market values.
Each symbol reports quantity, basis, close, market value, `nav_contribution`,
realized P&L, floating (`unrealized_pnl`) P&L, total P&L, cumulative commission
and adverse slippage. `nav_contribution` is exactly its marked position value;
there is deliberately no invented per-symbol cash allocation or standalone
per-symbol return denominator. Portfolio cash appears only once.

The portfolio also reports these cumulative costs and P&L totals. Entry cost
basis includes commission and slippage; whole-position exits realize net sale
proceeds minus the full basis. Slippage is disclosed separately but already
embedded in fills, never subtracted twice. Every day must reconcile exactly:
`NAV - initial_cash = realized_pnl + unrealized_pnl`. Orders include before/after
cash, fixed intent, quote/fill price, actual costs, status and rejection reason.
Signals, pending intents, and unique processed event IDs are preserved.

Arithmetic uses a fixed precision-64, half-even Decimal context. No taxes,
interest, FX, market impact, fee tiers, lot-size rules, shorting, leverage,
corporate-action income, delisting, liquidity, limits or actual matching are
modeled. Synthetic results are not investment performance claims.

## Integrity and recovery

Reports bind exact config and input byte SHA-256, complete package Python source
hash, model/version, execution policy and decimal precision. Resume verifies
those bindings and reproduces the entire saved prefix, including rejected
orders and pending intents, before continuing. Forging a report and updating
its checksum cannot bypass the prefix replay comparison. Hashes are integrity
bindings, not signatures. Whitespace changes to inputs or any package-source
change require a new run. Adding this module therefore changes the existing
package source hash: old pre-installation checkpoints need the old source tree.
The single-symbol replay's algorithm and file format remain unchanged.

For identical source and input bytes, all split-point resumes produce identical
final report and checkpoint bytes. Recovery is O(N), retains the full report
in memory, and requires the full unchanged dataset. This is not incremental
stream ingestion or continuous automatic checkpointing.

Outputs use existing hard-link atomic no-clobber publication. A valid checkpoint
can recover a crash before report publication into a new directory. The two
files are not one transaction, and filesystem power-loss durability is not
promised. Unsupported filesystems fail; existing output is never overwritten.
