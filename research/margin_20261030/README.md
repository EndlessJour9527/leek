# Financing changes and index association
Original2026-10-30 study: https://github.com/EndlessJour9527/leek/issues/26#issuecomment-6520600511 . Retained algorithm/protocol/aggregates, not a new run. ORIGIN.json pins original scripts. No raw daily prices/balances/aligned rows published.

242 available sessions2025-10-30..2026-10-29; requested end2026-10-30 lacks financing. Shanghai+Shenzhen financing only, not total financing-plus-securities-lending or Beijing. Fixed daily balance change rate; contemporaneous and next-session Pearson/sign groups reported in full. Correlation is not causal or profit evidence. No tuning, extra5-day exploration or independent holdout.

Publication/available_at unverified. Next close-to-close includes overnight movement; it is not a trade entered after publication. No executable signal return backtest or cost model. Missing market/date rows are omitted, never zero-filled. Source failures/latest-source rounding discrepancies remain in original private archive, not silently resolved by this publication.

Python3.10+, stdlib, without -O (original assertion guards required):
```
python -m unittest discover -s tests -p test_margin_association.py -v
python -m research.margin_20261030.analyze --input-dir /PRIVATE/frozen-margin-inputs
```
Real-input reproduction requires five privately retained files matching RESULTS.json hashes: margin.raw/margin_page2.raw result.data rows DIM_DATE/XOB_MARKET_0001/RZYE; SSEC/CSI300/CHINEXT.raw data.code and data.klines(date,open,close,...). Consumed hashes are provenance, not independent source authentication. No network or file writes; output aggregates only. Public synthetic tests are self-contained, real-input reproduction is not. Collection/independent verifier source remains private pending separate acquisition review; not every original artifact is synchronized. Formula unchanged; adaptation wraps input path and suppresses daily output/writes. Frozen window remains literal.

Portability regression found zero next-session pairs caused original mean() to fail; now emits n=0 and null metrics for that empty group. Frozen242-day result is copied unchanged; this guard is not new market evidence.

Defensive update rejects invalid numeric types, nonfinite/nonpositive balances and prices, and optimized Python. No paired samples returns explicit NO_PAIRED_SAMPLES_NOT_TRADABLE with null metrics. Frozen results unchanged: original Python3.9 reproduces exactly; Python3.12 sum rounding changes six correlations by at most7e-16, so cross-version equality is numerical, not byte-identical.
