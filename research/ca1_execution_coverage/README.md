# CA1 frozen model-trade execution-evidence coverage

This is a coverage check of existing model trades, **not a new return backtest or execution certification**. Local candidate; independent review pending. No strategy, budget, price, fill or ledger changes.

## Frozen diagnostic scope

Inventory all 151 existing CA1 fills (74 BASE, 77 DOUBLE), retaining order identities even when security and execution day repeat. Keep four model boundary rejections and three no-order records separate. Match security, signal/execution dates, applicable rule versions, direct security-day trading status, official reference/limit prices, corporate-action notices and date-only availability, opening timestamp and capacity evidence. Missing evidence stays UNKNOWN. Daily OHLC and end-of-day participation cannot certify opening fills. Later announcements cannot become signal-time knowledge.

The private diagnostic froze a complete 21-file input pin set before mapping. Missing or changed pins, duplicate identities, wrong accounts, dates or fixed counts fail closed. Public helpers extract the conservative date, identity and hash checks; they are not the full private archive adapter. The caller must separately freeze expected identities/pins. Matching hashes cannot prove provenance, economic truth or preregistration.

## Bounded aggregate findings

151 fills span 83 distinct security/execution days. All 151 lack a closed evidentiary chain for the applicable effective rule interval, direct security-day halt/resumption, official daily reference/limits, opening timestamp and opening capacity. UNKNOWN means not established by this archive, not proven false. 78 fills have archived derived daily-limit fields; the other 73 only have the registered model formula. Neither is an official daily limit tape.

80 fills link same-security notice originals; 71 have no listed notice, which does not prove absence of corporate actions. Of 398 order–notice links, 188 have a publication date before the signal date under the date-only EOD convention; 210 are later than execution and retrospective only. Four boundary rejection records represent two security/day cases in two cost scenarios; these are model rejections, not verified exchange-limit events. No private order dates, quantities, balances, daily prices or full matrix are included here.

The next evidence priority is official reference/limits and trading status for those two boundary cases, followed by opening auction evidence. This proposal does not authorize acquisition or relax existing data gates.

## Public reproduction boundary

From repository root:

```sh
python3 -m unittest discover -s tests -p test_ca1_execution_coverage.py -v
python3 -O -m unittest discover -s tests -p test_ca1_execution_coverage.py -v
```

These synthetic tests exercise the public helpers. They do **not** reproduce the private 151-fill matrix or validate the aggregate claims independently. The full archived-input adapter, fixed private pins, matrix, and verification instructions remain in the authorized private review package. No network or optional dependency is needed. Existing unrelated tests and historical returns were not rerun for this extraction.

## Archived public-source references

- [SSE 2023 trading rules release](https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20250612_10824490.shtml): archived general clauses 3.3.13, 3.3.17 and 4.3.1–3 support a formula framework; they do not establish official security/day values or every effective interval.
- [SSE 2026 rules release](https://www.sse.com.cn/lawandrules/sselawsrules2025/fund/trading/c/c_20260424_10817739.shtml): archived notice states July 6, 2026 effectiveness, after this frozen sample. Do not back-apply it.
- [SSE trading eligibility notice](https://www.sse.com.cn/lawandrules/sselawsrules/repeal/rules/c/c_20210531_5478094.shtml): eligibility rules are not direct daily halt/resumption evidence.

This work reads previously archived sources; it makes no claim that the URLs were newly fetched. No private archive/download links, machine paths, model responses or credentials are distributed.
