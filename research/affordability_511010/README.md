# Reproduction scope
Public package contains algorithms, synthetic tests, frozen cost/pin files and aggregate results only. Seven required private files are listed in INPUT_PINS.json and independently fixed in source EXPECTED_PINS; deleting/editing the supplied pin file cannot weaken the required set. Each actual body is SHA256-checked. Provider status/code must be integers, never booleans. Optimized Python is explicitly rejected. These are local snapshot bindings, not cryptographic provider authenticity.

Python3.10+ standard library. From repository root:
```
python -m unittest discover -s tests -p test_511010_affordability.py -v
python -m research.affordability_511010.analyze --root /PRIVATE/restored-M1 --output /PRIVATE/new-daily-result.json
```
Real-source calculation requires the privately held complete seven-file input tree, not included publicly. It writes ALL daily prices/results to the explicit private output path and refuses existing output. Do not publish that daily output. Public SUMMARY_PUBLIC.json contains aggregates. Private-only verify.py and RESULT_PRIVATE.json are supplied only in the separate authorized private archive; they are not required for public synthetic tests and cannot be run from this public repository alone.

The preserved original private archive documents the earlier incomplete pin validation failure. Current guards are fixed; numerical result unchanged. Preparation review confirmed1024 dates/4096OHLC/2048 costs, not a public-release approval. Local protocol timing has no independent trusted timestamp. Fixed initial budget counterfactual, not dynamic account performance. Original ML002 SSE/Tencent full-window gate remains blocked. No broker, new model, budget expansion or automatic promotion.
