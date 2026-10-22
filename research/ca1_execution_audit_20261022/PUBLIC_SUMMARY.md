# CA1 fixed-order execution-evidence audit — 2026-10-22

**PASS_FIXED_ORDER_RECONCILIATION_ONLY / BOUND / LIVE_NOT_CERTIFIED.** This is not a new strategy, return rerun, new independent market sample or live-trading approval.

Fixed source: PR10 head `0525b7b95b38433b962221deee08a50b9977ea99`.

- All **225 model fills and 6 NO_FILL** mapped to **90 date/instrument/side keys**: 88 fill keys, 2 rejection keys. Five NO_ORDER records retained separately.
- Independent review reconciled original orders, lock-before-execution chronology, opens, previous closes, model boundaries and rejection reasons. **No detected model-eligibility conflict.** 132 key/vendor open-and-previous-close checks and 42 fixed-source Git blob checks passed.
- 90 keys: 510300 ×48, 511010 ×1, 518880 ×41. No mapped order date coincides with a registered ex-dividend event.
- Boundary 2024-10-08 / 510300: model upper-bound rejection affects CA1_BASE/DOUBLE SELL700 each and SCASH_BASE/DOUBLE SELL600 each (four records).
- Boundary 2026-02-02 / 518880: model lower-bound rejection affects CA1_BASE/DOUBLE SELL200 each (two records).
- Scope-note correction adds the two SCASH records omitted from the first narrative table. The original complete matrix already included them. **No order, price, event, return or outcome changed.**

## What is and is not established
Archived vendor daily opens plus corporate-action inputs support reproducible **conditional daily-open research**. Official generic fund tick/limit provisions support a model formula; they are not day-specific status certification. No acquired official contradiction changes either rejection, but absence of found contradiction is not proof of eligibility.

For all 90 keys, exact execution-window status/exceptions, official daily reference/limit tape and own-order capacity/queue evidence remain uncertified. The observed daily bar is not proof of 09:30 tradeability. Historical rule-version continuity is bounded, not fully certified. These gaps are stated, not silently filled. No repeated polling or paid-data request is needed to finish this coverage audit.

Economic findings and the original development-only qualification are unchanged. Capacity, prospective evidence, user-authorized risk budget and stopping conditions are separate prerequisites for any future user-directed live validation. No brokerage connection or real order was made.

Public summary intentionally excludes original market-data series, PDFs, private links and private holdings. Full reproducible audit is a private evidence package with hash-pinned reuse of the previously published M1/M2 archives, not a new historical backtest.
