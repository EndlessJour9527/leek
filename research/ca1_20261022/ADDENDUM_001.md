# CA1 Addendum 001 — independent-review implementation clarifications

2026-10-22. Applies with immutable REGISTRATION_CA1.md SHA256
ecbfed5e725bd2722115d304c6d7e460948946318f00500cab23da3eecad0afa.
No economic thresholds, allocations, costs, dates or execution windows change.
No historical returns have been authorized by this clarification.

1. **Late-known action does not reverse history.** The ex-date cycle cancellation
   rule cancels only still-unexecuted orders/legs at the time information becomes
   available. If t+1 sale executed before an ex event on t+2 became known, retain
   the original sale, fees, cash and entitlement records. Cancel any outstanding
   affected buy order; never reverse the sale or manufacture restoration trades.
   Unknown conversion/reference still blocks the affected processing; unresolved
   entitlement/valuation makes the account INCOMPLETE, not a retroactive favorable
   fill. Previously completed economic events are immutable except a separately
   evidenced CORRECTION, which this rule does not authorize.

2. **Segment annualization.** Fixed inclusive segments are:
   2021-10-18–2022-12-30; 2023-01-03–2024-12-31; 2025-01-02–2026-06-30.
   For each segment, D=(literal calendar end date-literal calendar start date).days+1.
   CAGR=(end-close NAV / start-reference NAV) ** (365.25/D)-1.
   Start-reference NAV is 50000 for segment1, and preceding segment's end-close
   NAV for segments2/3. Calendar days outside these literal segments are not
   silently inserted; this is the frozen segment diagnostic convention. Accounts
   continue through the full exchange-session panel without cash/position resets.
   Annualized excess is CA1 segment CAGR minus SCASH segment CAGR for the same
   cost case, not annualization of a difference of raw returns. Zero excess counts
   nonnegative. Full-window CAGR retains its original inclusive window denominator.

3. **FIFO diagnostic allocation.** For a sell spanning multiple FIFO lots, allocate
   the actual sell fee and actual sell slippage SEPARATELY in proportion to sold
   quantities. Process oldest lot first (same-date tie: original fill event order).
   For every slice except the last, round_half_up(component_total*slice_qty/order_qty)
   to cents; assign the exact remaining component cents to the final slice.
   The original buy cost allocation remains proportional with exact remainder
   consumed at final lot close. Assert sum of slice principal/fee/slippage equals
   the original order, preserving the immutable portfolio cash ledger.

4. **Complete trades versus slices.** A complete round trip is one instrument's
   flat→positive holdings→flat EPISODE, allowing intervening partial rebalance
   sales/buys. Its net result is all episode sell proceeds minus all episode buy
   outflows (both include actual fees/slippage), plus all cash-distribution rights
   earned by episode holdings on record dates. Rights belong to that episode
   even if payment follows final sale; do not count them again in a later episode.
   When a right is known/fully valued, include its receivable once in episode net
   result even if unpaid. An unresolved right makes episode net result INCOMPLETE
   and excludes it from the *validated* complete-trade win-rate numerator and
   denominator; separately disclose incomplete episode count, never hide it.
   Open episodes at the end are not complete trades; floating P&L and all their
   dividends remain in portfolio NAV. Zero validated completed episodes means
   win rate/payoff/expectancy UNDEFINED. FIFO slice outputs are explicitly
   PRICE_AND_COST_SLICE_DIAGNOSTICS (exclude dividends), never complete-trade net
   win rates. This descriptive attribution cannot affect signals or executions.
