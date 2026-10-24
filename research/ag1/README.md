# AG1: a completed, rejected development hypothesis

**Decision: STOP_RESEARCH_VARIANT.** No parameter search to rescue this version.
This is a standalone archival research capsule, not an integration into the `leek`
execution engine or the H001/H002 pipeline. No broker, live account or promotion.

The only added rule was: at the frozen monthly 12-1 momentum decision, hold cash
when all four scores are nonpositive; otherwise retain the original Top2, 47.5%
each (including a negative second-ranked score). Zero is OFF, missing data blocks.
The inputs and interval had already been seen. These are developmental results,
not an untouched test, forward evidence or an investment recommendation.

## Result and frozen decision

2023-01-03 through 2026-06-30, each new comparison account starts at CNY 50,000;
accounts remain continuous within the interval. Training 2021-10-18–2022-12-30
calibrates target-exposure q = 151/297 without selecting q on returns.

| Base cost | CAGR | Max drawdown |
|---|---:|---:|
| AG1 cash gate | 14.26197% | 20.28294% |
| Original M12, same new interval | 16.71355% | 34.27125% |

The joint rule required drawdown reduction >=5pp, annualized opportunity cost
<=2pp, and CE3 above a training-fixed low-exposure M12 control, under BOTH base
and doubled costs. Drawdown improved 13.98831pp but opportunity cost was
2.45158pp; doubled costs also fail at 2.40943pp. The threshold is not revised.
Actual mean exposure differs (57.93% vs fixed-q 46.94%); no risk-matched alpha claim.
All eight paths, including losing periods, are in `results_ag1_v1/metrics.json`.
The immutable original decision file says its independent audit was PENDING at
creation; the subsequent completed audit is `audit/RESULT_AUDIT_AG1.json`.

Base model costs are 10bps commission, minimum CNY5, plus 10bps adverse slippage;
double reruns execution, not merely subtracting more costs from fixed trades.
Cash distributions and unrealized holdings are included. First-print daily
execution proxies assume sufficient liquidity; true queue/capacity is unverified.
This is not actual brokerage cost certification. 2026 H2 is excluded.

## What is public and what is not

- The original 1,486-line research source snapshot is separate from production
  core. Core code and all other PRs remain unchanged.
- All eight paths have full derived NAV/cash/cost/exposure series, model signals,
  model executions, corporate-action ledger events, terminal states and metrics.
- Vendor daily `marks` and raw OHLC datasets are NOT redistributed. Daily files
  are explicitly named `daily_derived.json`, not claimed byte-identical to the
  original full daily ledger. Provenance records each original file hash.
- Raw input archives, provider responses and original PDF evidence are excluded
  because public redistribution rights have not been established. No credentials,
  account holdings, private source URLs or local working paths are included.
- `audit/` contains archival audit records (internal reviewer labels generalized),
  not a new certificate for arbitrary data. Hashes detect changes, not authenticity.

## Reproduce the public verification (no market-data access)

From repository root:

```
python -m unittest discover -s tests -v
python research/ag1/run_public_tests.py
python research/ag1/verify_results.py
```

The capsule's 57 focused synthetic tests are a public subset of the original 62;
5 legacy registration/release tests require an omitted recovery record and are
not represented as passing here. Their original source is retained to preserve release pins; the explicit public
runner reports these two excluded modules. Full discovery requires the original
private recovery evidence and is not the public verification command.
Original economic audit and portable replay are historical evidence, not newly
performed by CI. CI verifies public derived results and synthetic accounting.

## Full historical replay: requires lawfully held original inputs

This public checkout alone cannot regenerate market-dependent results. Do not
substitute newly fetched data or change hashes to pass. `INPUT_ARCHIVE_HASHES.json`
lists six exact archive hashes; obtain those inputs with appropriate rights.
No private download links or new download authorization are supplied.

```
python research/ag1/restore_frozen_inputs.py --archive-dir /path/to/authorized_archives
cd research/ag1/implementation
python run_ag1.py --release ../audit/RUN_RELEASE_AG1.json --release-sha256 PUBLIC_RELEASE_SHA --output ../fresh_results
```

Replace `PUBLIC_RELEASE_SHA` with the SHA256 in `PUBLIC_SHA256SUMS.json` for
`audit/RUN_RELEASE_AG1.json`. It is a public copy of the archival release with
reviewer identity generalized; implementation and registration hashes remain
original. The original release hash remains in the old output manifest. Use
`PUBLICATION_PROVENANCE.json` to distinguish public transformations. Full replay
must retain `frozen_input/E4_H1_REPRODUCIBLE_v1` and its original 370-file manifest.
Its result manifest records the public release hash and therefore is NOT
byte-identical to the original manifest; economic outputs should be compared
separately. No data gate or DQ001 conflict is lifted.

## Publication provenance / licensing

Original AG1 package SHA256:
`3de505a41dd6b43ae79db01d6b10cabc6b1b61a9c005608877b0a146036527fd`.
Source is project-authored standard-library Python, with no copied third-party
library code; published under the repository MIT license. That license does not
grant rights to excluded vendor data or source documents. The preheat starts
2020-09-01, outside DQ001's five August 2020 dates; this is dependency exclusion,
not a declaration that either price vendor is always correct.
