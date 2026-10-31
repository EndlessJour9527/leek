# CA1 read-only diagnostics
Completed terminal stress: issue26; EOD capacity: issue27 in this repository. No strategy runs, network fetch, alpha or promotion. Previously seen development evidence only.

Terminal: eight frozen accounts at 2026-06-30, eight fixed scenarios each. CA1 BASE joint -20% loss is16.8354% of NAV; gold-only -20% loss6.0161%. SCASH is not pure cash. All64 scenarios retained. No probability, future safety or liquidation-cost claim.

EOD scope: CA1 BASE74/DOUBLE77 fills only; exclude4 NO_FILL and3 NO_ORDER. Not the comparator accounts. Before unit/source supplementation this audit was BLOCKED, not passed; original failures remain archived. All151 denominators now present;122 earlier candidates unchanged,29 supplemented. Maximum is0.019885367% for2021-10-20 511010 BUY, both costs. One bond fill per case provides no distributional evidence. All nearest-rank p50/90/95/99/max and side splits retained. No threshold chosen.

Unit evidence combines Sohu ninth-column 成交金额(万), supplier JS historySearchHandler rendering hq indexes unchanged, and original SSE2023 rules3.3.10–11 for fund per-unit RMB quotation (tick0.001RMB). It is not a formal Sohu API schema. Venue source: https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20250612_10824490.shtml . Current schema does not authenticate historical publication/schema stability. July2024 was retained archive cutoff, not API cutoff. Whole-day amount is ex-post, not known at opening; small participation cannot certify opening depth, queue, spread, limit handling or scalable execution. Portfolio turnover is not market amount.

Python3.10+, standard library, without -O (assert guards required):
```
python -m unittest discover -s tests -p 'test_ca1_*diagnostic.py' -v
python -m research.ca1_diagnostics.terminal_stress --results-root /PRIVATE/frozen-results
python -m research.ca1_diagnostics.eod_participation --root /PRIVATE/restored-extracted --evidence /PRIVATE/supplier-v2 --coverage /PRIVATE/capacity-coverage.json
```
Real-input reproduction requires separately authorized PRIVATE archives; public repository is not self-contained real-data reproduction. No original quotes, account daily/order arrays, private links or credentials included. EOD coverage is original private RESULT.json with cost/symbol/side/status/date/notional/candidate/pointer; evidence contains archived510300 arrays, root contains retained511010/518880 Sohu arrays. Output is aggregate only. Verify consumed hashes against original manifests: hashes are provenance, not authenticity. Portable adaptation only parameterizes paths and suppresses detailed rows; committed aggregates are copied unchanged, not a new history run.

Public EOD entry now pins the five frozen input SHA256 values in source, validates supplier security code, unique order identifiers and exact cost/asset/status counts, rejects noncanonical numeric strings/booleans, and refuses optimized Python. This is byte binding to the reviewed snapshot, not independent supplier authenticity. Protocol timing is locally recorded; no independent trusted timestamp or blind preregistration is claimed. Both aggregates remain byte-identical after defensive changes.
