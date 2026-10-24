# CA1 — fixed cross-asset allocation / M2 preregistration v1

Status: DESIGN_FROZEN_AWAITING_INDEPENDENT_REVIEW. NO_RETURN_RUN_AUTHORIZED.
Created 2026-10-22. This is one new research comparison, not an amendment to V1,
S01–S10, E4, AG1, any real account or any outstanding order. All history is seen
DEVELOPMENT data; no out-of-sample/alpha/live-readiness claim follows from success.

## 1. Question and exact paths
Does replacing cash with government-bond and domestic gold ETF exposure improve
net risk-return versus the SAME stock target weight, without selecting weights?
Four accounts, each independently initialized to CNY 50,000 cash at the opening
of 2021-10-18: CA1 = (510300,511010,518880) weights (1/3,1/3,1/3), SCASH =
(1/3,0,0), BH300 = (1,0,0), CASH = (0,0,0). Each runs BASE and DOUBLE costs,
exactly eight paths. Rational weights are exact fractions, never 0.3333.
SCASH has the same intended stock weight, NOT certified same actual exposure/risk.
BH300 trades only the initial cycle and then holds; CASH never trades. CA1 and
SCASH rebalance monthly. No parameter/weight/window/asset search or replacement.
The fixed reporting window is 2021-10-18 through 2026-06-30 inclusive, 1140 exchange
sessions. All assets use the SAME calendar and start/end. No annual reset, no
terminal liquidation, no invented sale fee. Open positions remain in final NAV.

## 2. Input binding and grade
Use M1's immutable raw/normalized calendar and CA package, including restored E4
510300 evidence. M1 final review is SHA256
65d75daabd585b0f2f7faaea76bb5c958ae77900cf38d417964bd30b7403e3c7;
M1 final manifest is SHA256
b399842c75c8ee5123be59ef9ff41566f25f07609b931262be61ad6c49e1bfc7.
The raw/CA files are not silently edited to replace ledger status strings: the
separate independent release supersedes their historical pending status.
M1 = PASS_BOUNDED_INPUTS_ONLY. Actual opening timestamp, capacity and complete
per-day halt/official limit records are NOT certified. Daily O is a first-print
opening PROXY, not a verified 09:30 fill. Use no later H/L to allow orders.
DQ001's five August 2020 dates are outside this panel; this run neither resolves
nor bypasses that separate conflict. A new conflict in this fixed panel blocks
this batch; it does not justify source voting or shrinking the window.

## 3. Deterministic signal and two-stage schedule
Initial signal t = 2021-10-18 CLOSE, when NAV=50,000 and shares=0. No order is
retroactively filled at that day's O. Other signals are the last exchange session
of each calendar month (including 2021-10-29); skip a cycle altogether if either
t+1 or t+2 is outside the reporting window. BH300 has ONLY the initial cycle.
At t close freeze NAV_t including marked shares, cash and unpaid receivables.
For each asset i: target_budget_i = round_cent(NAV_t * exact_weight_i), with any
one-cent aggregate overrun removed from the last nonzero code in ascending-code
order. target_quantity_i = floor(target_budget_i / C_i(t) / 100)*100.
No future O, return or volatility enters these targets. Sell quantity is
max(0, current_quantity-target_quantity); buy ceiling is
max(0, target_quantity-current_quantity). Freeze both at t. No cross-leg capital
redistribution when a leg cannot buy. No leverage, shorting or fractional shares.

Stage S: sells are valid ONLY at the t+1 opening proxy. Full frozen quantities
or NO_FILL; no partial fills, no later retry within this cycle. An unsuccessful
sale remains held until a new monthly signal, with a recorded reason. This is
scheduled rebalancing, NOT a stop-loss order. It does not cancel any old V1 exit.
Net sale cash joins total cash immediately but is restricted until t+2 pre-open.

Stage B: at t+1 CLOSE, freeze each buy order for t+2 OPEN. Target budgets and share
ceilings remain those fixed at t; do not recompute desired allocation using a new
NAV or tomorrow's price. For a buy-side leg, remaining leg budget = max(0,
target_budget_i - current_retained_quantity_i*C_i(t)), rounded to cents. For
clarity retained shares include any unsold shares; a leg scheduled to sell cannot
become a buy because its sale failed or prices moved. Select the largest 100-unit
q <= the frozen buy ceiling satisfying all-in reservation <= remaining leg budget
AND execution-date buying power. This is deterministic sizing AT ORDER LOCK,
not partial filling after an order was frozen. Reserve using raw C_i(t+1)*1.02,
rounded notional and separate costs as section 4. If q=0 record NO_ORDER.
Process ascending codes 510300,511010,518880, consuming reservations once. Buying
power includes already realized t+1 sale proceeds scheduled to release t+2, but
never hypothetical t+2 sale proceeds or unpaid distributions. Payment credited
at t+1 end-of-day is eligible, if evidence supports it. No overlapping cycle.
At t+2 open, fill the exact frozen q if eligible and funded; otherwise NO_FILL,
release reservation, no resizing, substitution, catch-up or chasing later prices.
Initial first purchases therefore occur 2021-10-20, not October 18/19. The two
initial cash days are included in every path's returns. No sell-stage quantity
is positive on the initial cycle. The first monthly cycle is separate.

## 4. Costs and modeled eligibility
Use Decimal and ROUND_HALF_UP to 2dp for each monetary component separately.
BASE: fee=max(5.00,round_cent(notional*0.001)); adverse slippage=
round_cent(notional*0.001). DOUBLE reexecution: fee=max(10.00,
round_cent(notional*0.002)); slippage=round_cent(notional*0.002).
Buy outflow=notional+fee+slippage; sell inflow=notional-fee-slippage.
No extra statutory stamp-tax line, dividend tax or hidden fee is added. This is
an explicit simplified gross-distribution ETF research convention, not a claim
about each investor's actual taxes/commission. Do not transplant it into old V1.
Reservation notional=round_cent(q*C_lock*1.02), then apply the same path costs.
DOUBLE is a full rerun with its own target/quantity/cash path. Also show a distinct
BASE-fixed-fill cost-doubling P&L sensitivity, not a second executable account;
report if hypothetical cash becomes negative, never call it feasible execution.

Buy gap O/C_lock-1 must lie in [-0.02,+0.02], inclusive. No such band on sells.
All fills assume sufficient opening quantity. All daily prints are conditionally
assumed tradeable unless supplied explicit adverse evidence; this is the bounded
model, not a verified historical status field. Missing/invalid raw prices,
unknown applicable CA conversion, known suspension, or identified inconsistent
reference/status evidence -> NO_FILL, not a guess.
Ordinary modeled limits: previous raw close minus a verified cash distribution
ex that day, rounded HALF_UP to 0.001; multiply reference by 1.10/0.90 and round
each to 0.001. O at or beyond either modeled boundary -> NO_FILL for either side.
Label MODEL_LIMIT_PROXY, not verified official daily limit. If actual supplied
limit evidence differs, STOP affected calculation for reconciliation before
returns; never use later H/L or favorable limit assumptions to enable a fill.
No return run until these calculations pass synthetic boundary tests.

## 5. Corporate action and daily event order
Date-only announcement availability is end-of-announcement-date, not invented
00:00. Later annual/H1 reports establish coverage, NOT historical signals.
Daily order: release prior-sale restricted cash; apply known ex-day receivable
recognition/reference bridge; process pre-frozen opening orders; close marks;
record-close entitlements; pay-date cash transfer at END OF DAY; register signals
and buy-stage reservations using that end-of-day cash state.
At record close save entitled shares from that account, regardless of later sale.
On ex date recognize exact entitlement*cash_per_share rounded to cents as
receivable; price mark is raw, shares unchanged. On pay date move receivable to
cash once, not new income again. No cash spending before pay. A later buyer gets
no past entitlement. Distributions are cash only and reinvested only via the next
scheduled allocation cycle; no automatic dividend purchase.
If ex date falls in [t+1,t+2] for a leg, cancel that leg's whole rebalance cycle;
this conservative predeclared policy avoids rewriting raw target units. Check
known ex events at t, and again before each opening for newly available evidence;
an unexpected unknown CA is NO_FILL/BLOCKED_CA, not a retroactive adjustment.
A record or pay date alone does not cancel a cycle. Existing holdings retain all
entitlements. Any split/fold not covered by immutable inputs blocks the batch;
no silent fractional/odd-lot deletion. No such events certified in this window.
NAV = total cash + all raw marked holdings + receivables - unbooked liabilities.
Missing valuation means NAV_INCOMPLETE, never zero return or forward-filled profit.

## 6. Frozen economic decision (not a statistical or live approval)
Primary comparator SCASH, not retrospectively whichever is easiest to beat.
For BOTH BASE and DOUBLE, CA1 must meet ALL:
A. CAGR_CA1 - CAGR_SCASH >= 1.00 percentage point;
B. CE3_CA1 > CE3_SCASH, where CE3 = 252*mean(daily_simple_return)
   - (3/2)*252*population_variance(daily_simple_return);
C. maximum daily-close drawdown_CA1 <= drawdown_SCASH + 5.00 percentage points.
These are explicit research utility screens selected before combined returns,
not estimates of statistical significance or a user-agreed real-money risk budget.
Failure of any => STOP_CURRENT_VARIANT; preserve all results, do not tune weights,
fee/risk thresholds or dates to rescue it. All pass => RETAIN_FOR_FURTHER_EVIDENCE,
never READY_FOR_LIVE. Full integrity failure => INVALID/BLOCKED, not economic FAIL.
Additional stability veto: CA1 annualized excess vs SCASH must be nonnegative in
at least TWO of the THREE pre-fixed segments 2021-10-18–2022-12-30,
2023-01-03–2024-12-31, 2025-01-02–2026-06-30 under both costs. Segment computation
uses the continuing account NAV and previous segment-end NAV; no restart.
Show segment excess without selecting them as new strategies.

CAGR = (NAV_end/50000)^(365.25/(calendar_days_inclusive))-1.
Daily return first day uses initial50000 as priorNAV; all 1140 days included.
MDD from initial NAV and all daily closes. Volatility sqrt(252)*population sd;
5% daily expected shortfall = arithmetic mean of worst ceil(0.05*N) daily returns.
Report underwater days/max spell, turnover=sum absolute buy/sell principal divided
by mean daily NAV (no /2), full round trips/wins/net payoff/expectancy when defined,
all open P&L including losses, dividends, fees and residual cash. For rebalancing
partial sales use FIFO lot accounting for descriptive closed-trade metrics only;
portfolio returns come from cash/share conservation. Zero sample => UNDEFINED.
Always display all eight paths, all NO_FILL/NO_ORDER reasons and actual stock/bond/
gold weights, target deviations and average exposures. Same stock target is NOT
same realized stock allocation; the primary evidence is total portfolio utility,
not certified alpha. Causal-source limits and single fixed historical window remain.

## 7. Research subscription cost — separate non-trading scenario
USD100/month = USD1200/year, 100% allocated to this project for a conservative
scenario, although the subscription may serve other work. Do not deduct it from
trade ledger or alter shares/risk to recover it. T=calendar_days_inclusive/365.25;
scenario expense_CNY=round_cent(1200*T*FX), FX={6,7,8} CNY/USD as FIXED SCENARIOS,
not observed exchange rates. Show terminal economic surplus=(NAV_end-50000)-expense,
and expense/50000. No fabricated reinvested NAV/CAGR after this off-ledger expense.
Capital-only fixed-cost burdens for {10000,50000,100000,200000} show 1200*FX/P per
annum, NOT scaled strategy returns or new whole-lot portfolio paths. Required
actual capital/loss tolerance still await user decision. Evidence may pass section6
while the subscription-adjusted economic case fails; state both, never hide costs.

## 8. Release, artifacts and exact stopping point
Before any historical combined performance: immutable data/config/code hashes,
independent design review, integrated synthetic tests, and independent run release.
Keep eight accounts, every cycle target/order/fill/rejection, daily holdings/cash/
receivable/restricted/reservation ledger, sources, all cost scenarios and metrics.
Hash-bind registration, source files, adapter and release; original E4/AG1 certificate
cannot authorize new logic. Preserve failures and append corrections; a correction
changing economics after results requires a new version, not overwrite.
No old account modifications, broker access, real-money actions or schedule changes.
