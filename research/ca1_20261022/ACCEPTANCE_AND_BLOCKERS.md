# CA1 minimal integrated release tests and implementation gaps

This is an acceptance specification, NOT a claim that tests already ran.
No additional provider, asset or outcome optimization is requested.

## Mandatory synthetic cases (independent exact-value assertions)
1. INIT/CAUSAL: initial signal Oct18 close, first buy Oct20; Oct18/19 NAV allcash.
   Mutating any future O/H/L/C cannot alter a previously frozen target/order.
2. MONTH/END: exchange monthend not calendar weekend; no cycle whose t+2 is outside
   fixed window; no final liquidation and no annual account reset.
3. SHARE_TARGET: exact thirds, half-up cent budget, deterministic last-leg cent
   adjustment; total target budgets never exceed NAV; one-lot bond affordability
   and unapplied remainder reported, no fictional exact-third realized weights.
4. BUY_LOCK: qty divisible100; desired ceiling fixed t; lock based on t+1close
   reserve and known cash; cheaper t+2 open does not increase qty, dearer one does
   not reduce qty or substitute another asset; no eligible100 -> NO_ORDER.
5. TWO_DAY_CASH: t+1 sold principal/fees counted once, totalcash receives net;
   restricted until t+2, available to t+1close's dated reservation only; release
   does not increase totalcash again. Hypothetical t+2 sales unusable.
6. CASH_ORDER: simultaneous buys ascending code, reservations no double use;
   insufficient funding cannot create negativecash, priority cannot change due
   to realized returns; unused leg budget is not reassigned as higher target.
7. SELL_FAILURE: sell is full frozen q at t+1 only or NO_FILL; rejected shares
   remain in NAV; no invented samecycle buy/exit retry, monthly later recomputation
   permitted; large negative sale gaps are not rejected by buy2% condition.
8. GAP/LIMIT: ±2% buy endpoints admitted; justoutside rejected. Modeledupper/lower
   boundaries reject BOTH sides; tick0.001 and excash reference have exact Decimal
   assertions. Future H/L changes never alter opening eligibility.
9. COSTS: base minimum5 and doubleminimum10, nonminimumrate cases, each component
   rounds half-up separately; actualnotional vs reservation; sale net can reflect
   full costs. DOUBLE fullreexecution vs BASEfixedfill diagnostic visibly distinct.
10. CA_RIGHTS: held recordclose -> exreceivable -> paycash exactly once; sold after
    record retains distribution; bought afterward gets none; ex mark raw with no
    double NAV dividend; receivable not spendable; paycash available only after
    definedendofday. Test real511010 four event dates and amounts, plus one510300.
11. CA_CYCLE: ex t+1/t+2 cancels affected leg cycle, record/pay alone do not;
    unknown CA fails closed; no unsupported fold/oddlot silently discarded.
12. INFORMATION: date-only announcement known only EOD, later report cannot enter
    signal; raw/normalized price missing/conflict leads INCOMPLETE/BLOCKED not
    zero/forwardfill. Historical ledgerpending string cannot override separately
    hash-bound independent CArelease, nor viceversa without source hashes.
13. CONSERVATION: daily cash and shares, restricted+free/reserved partition,
    totalNAV includes receivables and unrealizedloss. Exercise synthetic loser,
    allcash, partial rebalance exit and exactFIFO feeallocation. For partial FIFO
    lot close, allocate originalbuycost proportionally half-up and leave remainder
    on residual lot; final close consumes exact remaining cost; no lostcent.
14. METRICS: hand-check inclusive calendar CAGR, 252variance/CE3, MDD startingNAV,
    continuingsegment returns, tail tiehandling and ceil5% count, underwater days;
    zero completed trades -> UNDEFINED; account returns do not rely on FIFO labels.
15. ECONOMICS/STOP: fixture passing engineering but failing each A/B/C/stability
    must STOP; thresholds unchanged after outcomes. Eight paths all output.
16. FIXED_COST: FX6/7/8 scenario labels, no live-rateclaim; research expense never
    touches trade cash, lot quantity or tradingcost; other capital values yield
    only fixed-cost burdens, not pretend scaled portfolio performance.

## Must implement/verify before RUN_RELEASE
- Recover/reuse current multi-asset ledger and generic CA orchestration from
  repository at a pinned commit; no presumption PR3's prior 79 tests cover CA1.
  Do not fork a second inconsistent Ledger merely for this strategy.
- Add/verify the exact two-stage target/reservation/one-window cancellation protocol,
  ex-date leg cancellation and end-of-day dividend availability above. Existing
  engines' next-open assumptions are not silently equivalent.
- Link M1 immutable CA release to ACTION_LEDGER_V2 historical pending status and
  E4 510300 event evidence without editing originals. Fail if hashes disagree.
- Verify integrated record/ex/pay and modeled reference boundaries; M1's isolated
  four conservation examples are insufficient integrated-engine acceptance.
- Independent reviewer must bind protocol, implementation, exact test outputs and
  input files in a new RUN_RELEASE. No actual per-day capacity certification is
  promised; keep INPUTS_BOUNDED/CONDITIONAL_OPEN_PROXY grade in all results.
- No new input data gap presently established by M1 final audit. Any adapter
  discovery of cross-source conflict/CA gap stops affected run, not automatic
  generic demand for unattainable queue data or invention of zero distributions.

Known unresolved for LIVE, not obstacles to synthetic engineering: actual user
capital/loss budget, real commission/tax/custody, openingcapacity/status certainty,
contemporary prospective evidence, subscription cost allocation and explicit user
permission. No fixed 20day or winrate screen can replace those.
