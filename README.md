# Leek — evidence-based quantitative research

Standard-library research accounting, causal H002/H003 signals, conditional
historical runners and archived AG1/CA1 experiments. **Not a live trading system.**
The repository contains network-capable historical acquisition tools, but no
broker/account integration or automatic strategy promotion. Historical vendor
panels and private original evidence are not bundled or uploaded by CI.

## Current research entrypoint

```sh
python3 -m research.cli status
python3 -m research.cli preflight --experiment h002
python3 -m research.cli preflight --experiment h003
python3 -m research.cli preflight --experiment ca1
```

The first command is a status report, NOT an experiment. As of 2026-10-25, the
exact DQ001 5-day/20-cell source precedence is independently reviewed. H002/H003
still need replayable, hash-checked private inputs (**BLOCKED_INPUTS** in a bare
checkout); source availability and strategy completion are not implied. CA1
public accounting can be checked; full replay requires the private originals.
`research.cli` reports code, input readiness and experiment completion separately.
There is no inferred win rate or automatically qualified candidate.

See [DQ001 evidence and execution boundaries](docs/dq001-reviewed-source-precedence.md)
and [operations, restoration and acceptance](docs/research-operations.md).
The current-head `research-operations.yml` collects readiness on main/PRs;
real network experiments require an explicit manual `run`. A green readiness
collection job is not a profitable or completed backtest. No daily daemon is
created. Old real-history/H002 workflows remain manual compatibility entrypoints.

## Offline verification

```sh
python3 -m unittest discover -s tests -v
python3 research/ag1/run_public_tests.py
python3 research/ag1/verify_results.py
python3 research/ca1_20261022/verify_public.py
```

The core suite is synthetic. AG1/CA1 public validators check archived derived
accounting and hashes, not fresh market replay. The CA1 validator v2 uses explicit
checks under normal/-O/-OO execution and retains its original verifier/manifest.
Archived economic engines remain frozen and require nonoptimized Python.

## Research records

- [TradingAgents adoption decision and isolated comparison](docs/adr-tradingagents-research-boundary.md): strict offline evidence boundary, not an LLM trading strategy.
- [Frozen H002 protocol](research/H002_PROTOCOL.md)
- [Frozen H003 protocol](research/H003_PROTOCOL.md)
- [Data conflicts](research/data_conflicts.json): known conflicts are never overridden by a CLI flag.
- [AG1 rejected research archive](research/ag1/README.md): STOP_RESEARCH_VARIANT.
- [CA1 evidence archive](research/ca1_20261022/README.md): RETAIN_FOR_FURTHER_EVIDENCE, not live-ready.
- [Research charter](docs/research-charter.md): candidate budgets, independent validation and forward evidence.
- [Original core/module/replay documentation](docs/legacy-core-readme.md): historical module descriptions and demo commands, NOT a current project-readiness report.

All historical samples already examined remain development data. CI success,
branch merging and public report verification do not certify profitability,
full source-data reproduction or actual fillability. Source branches are cleaned
only after reviewed merge, final-head verification and dependency/SHA checks.
