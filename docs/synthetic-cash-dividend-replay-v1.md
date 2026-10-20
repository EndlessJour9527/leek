# Cash-dividend-aware synthetic portfolio replay v1

This additive entry point is an **offline accounting demonstration**, not a
historical strategy result, production release, or broker simulation service.
It does not change `leek.replay`, `leek.portfolio_replay`, their wire versions,
the independent H001 research branch, or any existing user's paper ledger.

## Run and recover

Python 3.10+; standard library only; no network or installation:

```sh
python -m unittest discover -s tests -v
python -m leek.cash_dividend_replay \
  --config examples/fixtures/cash-dividend-config.json \
  --input examples/fixtures/cash-dividend-bars.json --output /tmp/leek-ca-full
python -m leek.cash_dividend_replay \
  --config examples/fixtures/cash-dividend-config.json \
  --input examples/fixtures/cash-dividend-bars.json --output /tmp/leek-ca-part \
  --stop-after 4
python -m leek.cash_dividend_replay \
  --config examples/fixtures/cash-dividend-config.json \
  --input examples/fixtures/cash-dividend-bars.json --output /tmp/leek-ca-resume \
  --resume /tmp/leek-ca-part/checkpoint.json
cmp /tmp/leek-ca-full/report.json /tmp/leek-ca-resume/report.json
cmp /tmp/leek-ca-full/checkpoint.json /tmp/leek-ca-resume/checkpoint.json
```

Use fresh output paths. All old replay safety boundaries remain: exact JSON
fields and unique keys, raw bars, explicit complete calendar and fixed universe,
`synthetic: true`, `currency: SIM`, no forward fill, whole-share long-only targets,
fixed fees and adverse slippage, sell-first then explicit symbol priority,
all-or-reject next-session-open fills, and simplified later-date settlement.
These are research conventions, not exchange rules or achievable fill claims.

## Versioned contract

Both input and config use `synthetic-cash-dividend-replay.v1`. Config adds the
required field `corporate_action_policy`, fixed to:

`record-close.ex-before-open.pay-after-trading.gross-no-tax.v1`

The remaining fields match the portfolio v1 fixture. `corporate_actions` is an
explicit list (empty is allowed). Each event has exactly:

```json
{
  "event_id": "DIV1",
  "instrument": "AAA",
  "kind": "cash_dividend",
  "published_on": "2030-01-01",
  "record_date": "2030-01-03",
  "ex_date": "2030-01-04",
  "pay_date": "2030-01-06",
  "cash_per_old_share": "1",
  "split_ratio": "1",
  "rounding": "exact"
}
```

- IDs are bounded ASCII alphanumeric strings, unique **per instrument**.
- `published_on <= record_date < ex_date <= pay_date`. Publication is a supplied
  date, modeled as available by that day's end; it is not independently verified
  disclosure evidence and must not be used for intraday decisions.
- Record, ex and pay dates must all be listed sessions in the input calendar.
  The replay starts flat and cannot import a pre-window entitlement. A complete
  input must cover payments, even if a requested checkpoint stops before them.
  Non-session payments and cancellations/revisions are not inferred.
- Only positive bounded cash amounts, `kind: cash_dividend`, exact ratio `1`
  and `rounding: exact` are accepted. A dividend must be below the preceding
  session's raw close. At most one ex event per instrument per session; different instruments may
  have events on the same day and may reuse an event ID.
- Unknown fields, invalid ordering, duplicate IDs, missing dates, real data,
  taxes, splits/reverse splits, rounding, rights, spin-offs, cash-in-lieu,
  FX and other complex actions fail closed before output is created. Do not
  delete unsupported actions to make a dataset pass.

These limitations intentionally keep the increment smaller than the standalone
Ledger's CA capabilities. Split-aware pending quantities, target bridges and
fractional-share policies need a separate version and tests.

## Daily event order and accounting

1. **Before open:** call `Ledger.ex` for that day's event, using the previously
   recorded eligible quantity. Recognize a gross receivable and dividend income
   exactly once. Receivables contribute to NAV but are not spendable cash.
2. **Open:** execute orders fixed at the previous listed session's close. Sales
   precede buys, with configured priority. A sale after record preserves the
   dividend entitlement; an ex-day purchase creates no entitlement for this
   event. Execution never reads that day's close, high or low for sizing.
3. **After trading / close:** call `Ledger.record` on the resulting holdings.
   A record-day buy qualifies; a record-day sale removes those shares before
   the snapshot. This is a synthetic convention, not an exchange certification.
4. **After all trading:** call `Ledger.pay` for payment dates, including when
   pay equals ex. Move the receivable into cash; do **not** count new income.
   Payment cannot fund that day's opening orders. It can fund a later session.
5. Value at raw closes, reconcile, then form forward total-return signals.

No tax is deducted or reserved. `gross-no-tax` is explicitly a synthetic model
assumption, not a statement about an investor's tax treatment, and not approval
to change another paper account's tax policy. Full flat-position sales remove
cost basis; the implementation calculates basis removed from the Ledger rather
than assuming all pre-sale basis was removed.

For each instrument and the whole account:

`total P&L = realized trading P&L + unrealized trading P&L + cumulative gross dividend income`

`NAV = spendable cash + raw market values + unpaid receivables`

Commission is already in basis/proceeds; slippage is embedded in fill price and
reported separately, never subtracted twice. `nav_contribution` is market value
plus unpaid receivable, not an attribution of the shared cash balance. Income
stays attributed to its originating instrument after payment or a full sale.
`corporate_action_log` identifies record/ex/pay phases and eligible quantities
or amounts. It is a replay trace, not proof of exchange events.

## Signals and no future adjustment

At the first session set a per-instrument total-return level to its raw close.
For each later session:

`TR[t] = TR[t-1] * (raw_close[t] + cash_per_share_on_ex[t]) / raw_close[t-1]`

Use zero cash on non-ex dates. This market series is independent of the
portfolio's entitlement and payment date. It is a standard forward chaining
research convention, **not** actual reinvestment of the account dividend.
It never rewrites old levels when a future event is added. Compare TR at t to
TR at t-lookback; strictly greater selects the configured whole-share quantity,
otherwise zero. Signals become available at 23:59:59 UTC; orders still wait for
the next listed open. Terminal orders may remain pending with null execution.

Comparisons use exact `Fraction` arithmetic over decimal input strings so a
return to an identical level cannot create rounding-induced positive momentum.
Displayed `total_return_level` is rounded under the isolated 64-digit Decimal
context; it is not the authoritative comparison value. With no actions the
comparison is mathematically equivalent to comparing raw closes.

The entire input is validated up front as an integrity gate, so invalid future
bars/events can block a run. Given valid inputs, later events/prices do not feed
earlier account actions or signals. The reported input hash does bind the full
bundle; changing even future data invalidates old checkpoints intentionally.

## Recovery and verification limits

The report/checkpoint, exclusive immutable writes, SHA-256 source/input/config
binding, prefix re-execution and repeat-resume rules follow portfolio v1.
`corporate_action_policy` and the new signal model are additionally bound. A
checkpoint at record, ex, an unpaid interval or payment replays and verifies all
phases, so it cannot double-pay on resume. Reports include the entire prefix;
this is not efficient streaming, an incremental-live ingestion service, a
signed audit log, or a transaction with a real broker.

Adding this module changes the existing all-package Python source fingerprint.
Pre-upgrade checkpoints from any entry point will therefore be rejected. They
must be rerun under their original source version or regenerated honestly;
never edit hashes to force them through.

Tests exercise record/ex/pay timing, zero and cross-instrument entitlement,
no same-day payment funding, gross income/NAV reconciliation, no future
adjustment, unsupported-action rejection, and every session's resume boundary.
They do not establish profitability, actual data availability, complete
corporate-action coverage, exchange legality or real-world execution quality.
