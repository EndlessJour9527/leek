# Independent CA1 public-capsule review

Reviewed 2026-10-22 UTC by a separate publication reviewer. **PASS_BOUNDED_PUBLICATION_REVIEW** for the reviewed capsule. This is not a live-trading certificate, new economic experiment, data redistribution licence, or remote-CI attestation.

## Checks actually performed

- Compared all 22 transformed result files against frozen original objects and their declared source SHA256. Exact equality after deleting only `daily[*].positions[*].close`; no other result value changed. This covers 9,120 primary daily rows across all eight registered paths plus 4,560 fixed-fill sensitivity rows. The latter are diagnostics, not extra independent strategy samples.
- All eight registered account/cost combinations appear in SUMMARY and full derived accounting paths. No loser omitted; repeated reproduction is not additional market evidence.
- Implementation source, runner, 16-test suite, independent 5-test execution suite, independent metric script, original registration/addendum/acceptance and final historical audit are byte-identical to frozen originals. Vendored Ledger is byte-identical to the repository main Ledger and covered by the repository MIT licence; no external library code was introduced.
- Executed the 16 public implementation synthetic tests and 5 independent execution synthetic tests: all 21 passed. Historical INPUTS is deliberately absent, so the original integrated historical-calendar-dependent suite is not represented as public CI coverage. The archived historical audit's 22+5+15 counts refer to its original scope, not these public commands.
- Inspected file inventory and text for private website addresses, internal workspace paths, message IDs, personal financial data/holdings, credentials, original provider raw files, normalized OHLC panels and PDFs; none found in the reviewed tracked capsule. Simulated CNY50,000 and USD100/month are explicitly generic research assumptions, not disclosures of actual finances.
- Derived holdings, execution prices, values and quantities are accounting outputs and can imply some prices. The README explicitly disclaims original-data licensing; this publication review does not grant rights to separately obtained market data.
- Retained 72.55% gold contribution, zero completed flat-to-flat episodes/undefined win rate, generic full-subscription FX7 economic surplus −17,072.04, all-seen-development limitation, conditional execution assumptions, and `RETAIN_FOR_FURTHER_EVIDENCE` / not-live-ready conclusion.
- README distinguishes original archived manifest/run-release/audit hashes from transformed public contents; full historical replay requires the lawful original complete hash-bound inputs and excluded evidence/preparation files. Checkout does not claim complete historical reproduction or fresh independent historical validation. Existing account/order rules and unrelated data-conflict gates are unchanged.

## Scope limits

Public verifier/workflow and remote commit/CI need final maintainer verification on the exact published head. No new historical return run was performed in this publication review. The historical audit remains evidence about the original private frozen run only. Human authorisation and risk limits, unseen evidence, actual execution/capacity and economic viability remain separate gates.

## Final compression and verifier check

The eight primary path and four fixed-fill diagnostic JSON files (12 total) were deterministically gzip-compressed (mtime=0). Independent decompression and structural comparison against original objects reconfirmed all 22 results unchanged except the declared daily closing-mark removal. TRANSFORMS uses logical uncompressed names; compressed public bytes are separately bound by PUBLIC_MANIFEST. Reviewed public verifier checks manifest hashes, all 9,120 NAV identities, absence of closing-mark fields, zero complete round trips, and retained decision. This is accounting validation, not market-input replay. Workflow runs the stated synthetic suites and public verifier on Python 3.10/3.12; exact-head remote CI remains publisher responsibility.
