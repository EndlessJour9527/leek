# Research convergence checkpoint — 2026-10-21

## Stop current versions, preserve evidence

| Version | Decision | Reason / retained use |
|---|---|---|
| MA120 dual-ETF | Stop optimizing this alpha claim | Main economic screens failed; lower exposure is not alpha. Preserve as a trend/risk reference. |
| E4 M12 | Stop lookback/TopK search | Phase stability failed; returns concentrated in growth exposure and later recovery. Preserve frozen comparator. |
| R2 VT10 | Stop current risk-scaling variant | Risk fell, but opportunity cost exceeded the frozen limit; increment over fixed reduced exposure was unstable. |
| AG1 | STOP_RESEARCH_VARIANT | Both cost cases fail the pre-outcome 2pp CAGR opportunity-cost limit. See complete public capsule. |

These decisions apply to the exact tested versions, not all trend, allocation or
risk-management methods. Tests/PRs are engineering evidence, never profitability.
Existing H001/H002 work and DQ001 remain separately governed; no old account rules
or frozen simulated orders are changed by this research checkpoint.

## Next single question: cross-asset static allocation feasibility

Can government-bond and gold exposure replace part of cash at the SAME stock
target weight with a net risk-return increment? Candidate instruments: 510300,
511010, 518880. Identity checks are not historical-data approval. No new return
has been run, no weights optimized, and no replacement asset or favorable window
may be chosen silently if a candidate fails data qualification.

Two workstreams, not a requirement to fill a fixed number of trader roles:
1. Data: common daily panel 2021-10-18–2026-06-30, original source responses and
   hashes, corporate-action record/ex/pay/fold events, calendars, status, units.
2. Independent review: data grades and attainable whole-lot weights/costs at a
   declared experimental capital; freeze one allocation and a stock-weight-matched
   cash comparator BEFORE looking at the combined strategy output.

## Milestones and non-negotiable stops (UTC+8 dates)

- **2026-10-23:** data feasibility PASS or BLOCKED, exact missing evidence. An
  unexplained price conflict, action gap or instrument/unit ambiguity blocks the
  affected combination; no zero-fill, shortened window or moving goalpost.
- **2026-10-25:** only if data and frozen protocol pass, run the single registered
  experiment and independent audit. Otherwise report NO-GO with the failed gate.
- **2026-10-26–28:** assess real-world lot/cost/execution constraints and a separate
  risk/stop plan; absence of sufficient evidence remains NO-GO.
- **2026-10-28:** explicit readiness decision. Calendar deadlines NEVER establish
  qualification. Any later human-operated limited execution trial requires a
  separate decision and explicit capital/loss/stop budget, not automatic promotion.

Research subscriptions and other fixed operating costs must be presented as a
separate, declared allocation scenario, not quietly added to historical trade
fees or used to justify leverage. No positive result or recovery of costs is
promised. This plan does not authorize a brokerage connection or actual trading.

Outputs: a three-asset qualification matrix, action ledger and gap list, immutable
input manifest, minimal conservation tests, then (only after release) all registered
results. All reused history is seen development data, not untouched validation.
