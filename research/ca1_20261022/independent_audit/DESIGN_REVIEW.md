# CA1 independent design review — 2026-10-22

**DESIGN_PASS. IMPLEMENTATION/RUN RELEASE PENDING. NOT LIVE CERTIFICATION.**

Reviewer: audit_cross_asset_registration, separate from protocol author and implementation author. No historical combined performance run or parameter selection performed in this review.

## Immutable scope
- REGISTRATION_CA1.md SHA256 ecbfed5e725bd2722115d304c6d7e460948946318f00500cab23da3eecad0afa
- ACCEPTANCE_AND_BLOCKERS.md SHA256 564720a8e2c321199323145a05982cc6255786fcb39389aa2ae4d39009860174
- ADDENDUM_001.md SHA256 b7a84a5809b35b050e07f75bdd22950a2a180eae22cf3b6418fb48f9cec82aa8
- M1_FINAL_INDEPENDENT_REVIEW.md SHA256 65d75daabd585b0f2f7faaea76bb5c958ae77900cf38d417964bd30b7403e3c7
- M1 SHA256SUMS_FINAL.json SHA256 b399842c75c8ee5123be59ef9ff41566f25f07609b931262be61ad6c49e1bfc7
All above hashes independently read and verified locally.

## Accepted design
1. One mechanism, fixed stock/bond/gold thirds, 4 comparisons x 2 independently executed costs. SCASH is same stock-target, not actual same risk/exposure or alpha control. Exact initial budgets 16666.67/16666.67/16666.66; final quantities remain all-in cost/round-lot limited. Residual cash and realized weight deviations must be shown.
2. Initial close signal 2021-10-18; first buy 2021-10-20. Month-end signal freezes NAV/targets/sell and buy ceiling. t+1 opening sells, t+1 close buys lock against original leg budget and now evidenced sale proceeds, t+2 buys. No anticipated sale cash, retroactive locks, affordable quantity expansion or within-cycle retries.
3. Record/ex/pay rights, ex-date cycle cancellation, payment-only spendability and no forced dividend reinvestment are explicit. Date-only publication means EOD. Prior-event holdings remain despite missing downstream data. Addendum prohibits reversing an already filled sale when a later ex event becomes known.
4. Public first-print open, sufficient quantity and ordinary modeled limit bounds are conditional assumptions, not verified 09:30 execution/status/capacity. Known contradictions and unsupported CA fail closed. No use of later H/L for execution eligibility.
5. Base and doubled minima/rates are independently rerun. Fixed-fill doubled-cost diagnostic is separate. All NAV includes floating losses/receivables/costs, continuous across segments, no terminal forced liquidation.
6. Three fixed segments, literal inclusive annualization, >=1pp CAGR increment, CE3 greater, MDD tolerance <=5pp and >=2/3 nonnegative segment excess must hold for BOTH costs. Failure stops this variant; no parameter rescue. This is an economic utility screen on already-seen development data, not statistical proof or live permission.
7. Subscription USD100/month, fixed FX 6/7/8 and capital-only burden scenarios remain outside the trade ledger. User actual capital/loss budget not supplied; this is not an assumed real portfolio.
8. Complete trades mean flat-to-flat instrument episodes with fees/slippage and earned dividend rights. FIFO slices are price/cost-only diagnostics, never substituted for complete net win rate.

## Required implementation evidence (not yet certified)
Bind final code/adapter/data/protocol; complete 16 acceptance groups, real-event synthetic CA and independent metrics tests. Check boundary comparators, complete 3-segment presence, separately rounded FIFO component remainders and complete-episode attribution. Existing M1 certificate and this DESIGN_PASS do not authorize historical returns; a separate hash-bound RUN_RELEASE is required. Preserve all test failures and corrections. Do not overwrite any prior account or research result.
