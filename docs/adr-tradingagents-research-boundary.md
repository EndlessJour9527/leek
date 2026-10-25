# ADR: Selective adoption of TradingAgents, with an isolated upstream comparison

Date: 2026-10-25. Status: architecture decision accepted for research engineering;
the first slice below is an offline evidence boundary, not a deployed LLM strategy.

## Decision and ownership

Leek remains the deterministic accounting, execution-assumption and evaluation
system. LLM research is a separate producer of **research proposals**, not orders.
An upstream TradingAgents fork may run separately as a comparison. Installing or
successfully running that fork does not replace Leek, validate profitability, or
grant permission for real trading.

The referenced upstream version is `TauricResearch/TradingAgents` commit
`e8f5503e9b86d5c2710b0c76b1f686703968c9df` (v0.7.0). This change borrows design
ideas, not implementation code, and adds no upstream runtime dependency. Any later
copying of Apache-2.0 code must retain the applicable license and notices.

## What is adopted now

| Mechanism | Leek decision | Concrete boundary |
| --- | --- | --- |
| Point-in-time evidence | Adopt an immutable evidence packet | Source identity, publication/availability/capture times, content hashes and packet binding are mandatory. |
| Structured proposal | Adopt a strict research contract | Thesis, evidence references, counter-evidence or a bounded negative-search statement, and an invalidation condition; never infer an order from prose. |
| Opposing review | Adopt a separate challenge artifact | Bind the same packet and exact candidate; cover every item in the fixed packet, including uncited items; reject self-review identifiers; material unresolved contradiction means review/abstention, not a majority vote. |
| Missing-data abstention | Adopt fail-closed handling | Invalid, missing, future or mismatched inputs do not become neutral values or a valid trading signal. |

These controls are implemented by `research/evidence_boundary.py`. They check
declared structure, temporal consistency and hash/reference integrity. They do
**not** establish that a source is truthful, a timestamp independently attested,
two different producer identifiers are genuinely independent people/models, or
the research thesis is economically correct.

Review scope is the entire supplied, bounded packet, not all potentially relevant
information in the world. An omitted packet item is rejected even when the
candidate never cited it. URI syntax is checked, with explicit synthetic versus
observed provenance; URL reachability and source authenticity are not checked by
this offline module. A negative-search declaration refers only to the frozen
packet and is not evidence of an external web search.

## What is deliberately deferred or rejected

- **Defer automatic experience memory.** An outcome can enter future research
  only after its actual availability time. Reusing a log across backtest dates or
  experiment versions risks leaking outcomes. The first slice has no memory store.
- **Defer multiple debate rounds and orchestration dependencies.** A single
  independent challenge is the initial design. More rounds or LangGraph are not
  justified until a controlled comparison shows incremental value relative to
  their latency, model usage and operational complexity.
- **Defer model clients and automated report generation.** The first slice
  consumes explicit JSON; it does not claim to have run multiple models. The
  isolated upstream deployment is separately authenticated and measured.
- **Reject free-text fallback for machine acceptance.** Unparseable JSON or
  unrecognized order-like fields are invalid, never an implicit Buy/Sell.
- **Reject LLM approval as a hard-risk override.** Cash, sellable quantities,
  corporate actions, state restrictions and costs remain programmatic. There is
  no connection from this module to order creation or the frozen strategies.
- **Reject upstream decision scoring as account performance.** Its current
  backtest explicitly has no quantities, fill prices or cash ledger. Do not import
  its rating hit rate or interval alpha as Leek net return, drawdown or win rate.
- **Reject upstream price/fundamental feeds as automatically certified A-share
  inputs.** Date filtering does not certify adjusted-price factors, company-action
  history, as-filed A-share financials or a model's internal historical knowledge.

## Time and information semantics

`as_of` is the **evidence cutoff**, not a claim that all analysis was finished at
that instant. Source publication and availability must not exceed it.

For `forward_shadow`, the evidence must already have been captured by the cutoff.
Packet, candidate and challenge creation times must be ordered. Normal analysis
may finish after the cutoff; the eventual decision-availability timestamp must
reflect that, and cannot be backdated into a past fill window.

For `historical_development`, evidence may be collected later, but its supplied
publication/availability still has to precede the cutoff. Such a packet is labeled
`ALL_SEEN_OR_RECONSTRUCTED`, not an untouched historical test. A forward label alone
also does not certify a clean holdout. No self-declared timestamps or hashes are
external time attestation, and no claim about LLM training-data contamination is
made by this validator.

## First executable increment and acceptance

The complete narrow path is: a supplied packet, proposal and challenge are read,
validated together and converted into a deterministic research-only report.
Reports distinguish accepted research material, explicit abstention, unresolved
review and invalid input. Every result denies execution authority and profit
evidence. The implementation has no network calls, model billing, broker access,
portfolio mutation or dynamic strategy switching.

Synthetic fixtures cover historical acceptance, forward acceptance, contradictory
review, explicit abstention and future-data rejection. They are not market
observations or generated LLM performance samples.

```sh
python3 -m research.evidence_boundary examples/fixtures/research-evidence/historical-accepted.json
python3 -m unittest discover -s tests -v
```

Acceptance requires deterministic expected output, rejection of altered hashes,
foreign-run artifacts, missing references, self-review, future inputs, invalid
timezones and unstructured/order-like input. Protected ledger, replay, H002/H003,
DQ001 and existing `research.cli` files must remain unchanged. A green test suite
accepts this boundary implementation only, not a profitable strategy or a complete
multi-agent research service.

## How the independent fork will be compared

There are three different questions; they must not be conflated:

1. **Operational smoke test:** can the pinned fork run on the selected Mac mini
   with explicitly authorized subscription access, bounded settings and retained
   configuration? This establishes installation/authentication only.
2. **Research-quality experiment:** compare a deterministic-rule baseline, a
   single-model report and a compact multi-role report on the same frozen evidence
   cases. Record cited-fact correctness, timestamp violations, contradictory
   claims, abstention, repeated-run variability, model calls and observed usage.
   Include counterexamples and failures, not only fluent reports.
3. **Economic experiment:** only after a separately registered mapping from a
   research output to paper intentions exists, replay all groups through the same
   capital, costs, tradeability and accounting model, with risk/exposure-matched
   controls. Current frozen accounts and parameters are never silently changed.

The first increment implements none of the model comparisons or economic runs.
No backfilled performance, expected return or measured API cost is claimed.
Initial comparison should use a small fixed case set and one challenge round;
do not launch a full-market, multi-year LLM grid before establishing input quality
and measured resource use. A small operational sample cannot qualify live trading.

Adoption is reversible: if the challenge layer adds expense without improving
verified research quality, retain the simpler producer. Preserve the complete
experiment history. Do not tune on a consumed sample and call it unseen again.

## Primary references

- [Upstream scope: decision scoring, not portfolio simulation](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/backtest.py#L1-L15)
- [Structured-output fallback which is not adopted here](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/agents/structured.py#L59-L95)
- [v0.7.0 decision-time scoring correction and memory upgrade caveat](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/CHANGELOG.md#L7-L20)
- [Upstream Yahoo adjusted-price acquisition](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/dataflows/vendors/yahoo/ohlcv.py#L161-L230)
- [TradingAgents paper v7](https://arxiv.org/pdf/2412.20138v7)

