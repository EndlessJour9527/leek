# CA1 public research capsule — retained, NOT live-ready

2021-10-18–2026-06-30; 1,140 sessions; ALL_SEEN_DEVELOPMENT. Four fixed accounts × two costs, no winner selection. All eight paths included. Economic decision **RETAIN_FOR_FURTHER_EVIDENCE**, not certification or trading permission. See RESULTS.md and original archival independent audit.

## Public scope and reproduction boundary
Original standard-library source and frozen protocol, aggregate/derived accounting paths and costs are published. Daily raw closing marks are removed from positions; there is NO raw OHLC or normalized price panel, original announcement PDF, private URL or client data. Quantities/value may imply prices: derived accounting is not a license for original market data. Original source/audit hashes are archived, not falsely rebound to transformed public files. TRANSFORMS.json records every result transformation; PUBLIC_MANIFEST.json binds the public capsule.

`implementation/vendor/ledger.py` is unchanged MIT-licensed Leek Ledger; repository LICENSE applies to original code. No external library or market-data redistribution license is granted.

Checkout supports synthetic tests and independent derived accounting verification, NOT full historical replay. Full replay requires lawful separately obtained original inputs AND all exact files listed in IMPLEMENTATION_MANIFEST.json, matching archived RUN_RELEASE.json, including excluded preparation code/evidence files. No dummy prices or regenerated certificates may substitute. Missing originals fail closed. Original final audit attests the private frozen original run, not a fresh public CI historical rerun. No new independent market sample is claimed.

## Commands (from repository root)
```
python -m unittest discover -s tests -v
PYTHONPATH=research/ca1_20261022/implementation python -m unittest discover -s research/ca1_20261022/implementation -p test_ca1.py -v
PYTHONPATH=research/ca1_20261022/implementation python -m unittest discover -s research/ca1_20261022/independent_audit -p test_execution_independent.py -v
python research/ca1_20261022/verify_public.py
```

## Decision and next work
Base CAGR8.198%, MDD10.904%; double7.988%/10.983%. Gold supplies72.55% of base profit; SCASH matches intended equity weight, not realized risk. 0 flat-to-flat episodes means undefined win rate. At generic50k capital, $100/month fully attributed and hypothetical FX7 gives−17,072.04 economic surplus. No capital increase recommendation.

Next: execution/cost/capacity and concentration stress, independent evidence plan, explicit GO/NO-GO. Do not optimize weights to salvage this history, call repeated runs independent evidence, auto-merge or deploy live. Existing failed variants and unrelated data-conflict gates remain unchanged.

Large result JSONs are deterministically gzip-compressed (mtime=0), lossless; decompress before parsing. TRANSFORMS paths refer to uncompressed logical names.
