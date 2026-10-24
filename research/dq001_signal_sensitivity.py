"""Bounded CLOSE-SIGNAL sensitivity to the already-known DQ001 five-day quote conflict.

This is NOT a historical execution replay and cannot resolve DQ001. It consumes
only an archived derived buy-and-hold *account* exported by an older, already-
seen research run, never downloads data or runs an optimizer. The source is
explicitly pinned by the SHA256 of the JSON entry inside the workflow artifact.
No original or implied daily prices are printed or committed.

Usage from repository root:
  python -m research.dq001_signal_sensitivity --artifact /path/to/artifact.zip
  python -m research.dq001_signal_sensitivity --artifact /path/to/artifact.zip \
      --output /new/path/report.json
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

from leek.channel_signal import CloseChannel2010
from leek.mean_reversion_signal import MeanReversion20

ARCHIVE_RUN = "https://github.com/EndlessJour9527/leek/actions/runs/39446205344"
ARCHIVE_ARTIFACT_ID = 12276081553
EXPECTED_BUYHOLD_SHA256 = "53e5cfb1a67849a7cb5eb631817edadc63b3057426f305bbb06ad72bf76990de"
EXPECTED_AUDIT_SHA256 = "c4790fd5fff383b959b732b02af7172c24eb6c72187d72fb34e61eaab213e763"
DISPUTED_DATES = ("2020-08-21", "2020-08-24", "2020-08-25", "2020-08-26", "2020-08-27")
TICK = Decimal("0.001")


class SensitivityInputError(ValueError):
    """Evidence missing or incompatible: do not emit a success-shaped result."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise SensitivityInputError(reason)


def parse_archive_entry(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as z:
            info = z.getinfo("base__buy_hold.json")
            require(info.file_size <= 2_000_000, "archive entry size out of allowed range")
            content = z.read(info)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise SensitivityInputError("missing/unreadable pinned buy-hold archive") from exc
    require(sha256(content).hexdigest() == EXPECTED_BUYHOLD_SHA256,
            "derived buy-hold report SHA256 mismatch")
    try:
        return json.loads(content, parse_float=Decimal)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise SensitivityInputError("invalid archived account JSON") from exc


def extract_closes_and_dividends(account: dict) -> tuple[list[str], dict[str, Decimal], dict[str, Decimal]]:
    daily = account.get("daily")
    require(isinstance(daily, list) and len(daily) == 1455, "unexpected account row count")
    days: list[str] = []
    closes: dict[str, Decimal] = {}
    for row in daily:
        try:
            day = row["date"]
            qty = int(row["quantity"])
            value = Decimal(row["market_value"])
            require(qty == 2400 and value > 0, "reference quantity/valuation changed")
            close = value / qty
            require(close > 0 and close / TICK == (close / TICK).to_integral_value(),
                    "cannot derive an exact quote tick from archived account")
            require(day not in closes, "duplicate date in archived account")
            days.append(day)
            closes[day] = close
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise SensitivityInputError("malformed archived daily row") from exc
    require(days == sorted(days) and days[0] == "2020-01-02" and days[-1] == "2025-12-31",
            "archived account calendar changed")
    events = account.get("corporate_action_log")
    require(isinstance(events, list), "corporate action log absent")
    quantities = {}
    for event in events:
        if event["phase"] == "record":
            require(event["event_id"] not in quantities, "duplicate dividend record event")
            quantities[event["event_id"]] = int(event["quantity"])
    dividends: dict[str, Decimal] = {}
    for event in events:
        if event["phase"] != "ex" or event["date"] not in closes:
            continue
        day = event["date"]
        require(day not in dividends, "multiple ex-dividend events not supported here")
        qty = quantities.get(event["event_id"])
        require(qty == 2400, "missing/changed dividend entitlement in reference account")
        amount = Decimal(event["amount"])
        require(amount > 0, "invalid ex-dividend cash amount")
        dividends[day] = amount / qty
    require(len(dividends) == 5, "unexpected historical ex-dividend count")
    return days, closes, dividends


def extract_disputes(path: Path, closes: dict[str, Decimal]) -> dict[str, Decimal]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SensitivityInputError("missing pinned source-disagreement audit") from exc
    require(sha256(raw).hexdigest() == EXPECTED_AUDIT_SHA256, "source audit SHA256 mismatch")
    try:
        audit = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SensitivityInputError("invalid source audit") from exc
    rows = audit.get("mismatches")
    require(isinstance(rows, list) and len(rows) == 20, "unexpected number of source disagreements")
    cells = {}
    other = {}
    for r in rows:
        try:
            key = (r["date"], r["field"])
            require(key not in cells, "duplicate source disagreement cell")
            require(r["field"] in ("open", "close", "high", "low"), "unexpected field")
            eastern = Decimal(r["eastmoney"])
            tencent = Decimal(r["tencent"])
            require(eastern - tencent == TICK, "source difference not exactly one tick")
            cells[key] = True
            if r["field"] == "close":
                require(closes[r["date"]] == tencent,
                        "derived archive close does not match pinned Tencent evidence")
                other[r["date"]] = eastern
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise SensitivityInputError("invalid price source disagreement cell") from exc
    require(set(cells) == {(d, f) for d in DISPUTED_DATES for f in ("open", "close", "high", "low")},
            "scope of source disagreement changed")
    return other


def exact_levels(days: list[str], prices: dict[str, Decimal],
                 dividends: dict[str, Decimal]) -> list[Fraction]:
    """Mirror the frozen Ledger total-return close recurrence, not fill logic."""
    levels: list[Fraction] = []
    for i, day in enumerate(days):
        close = Fraction(prices[day])
        level = close if i == 0 else levels[-1] * (
            close + Fraction(dividends.get(day, Decimal(0)))
        ) / Fraction(prices[days[i - 1]])
        levels.append(level)
    return levels


def different_state_days(days: list[str], left: list[Fraction], right: list[Fraction],
                         first_index: int, model_class: type, initial_state: bool) -> list[str]:
    """Hold the same previous-20 days and BOTH possible initial regime states."""
    require(first_index >= 20 and len(days) == len(left) == len(right), "insufficient history")
    a, b = model_class(), model_class()
    a.history.extend(left[first_index - 20:first_index])
    b.history.extend(right[first_index - 20:first_index])
    a.state = b.state = initial_state
    differences = []
    for idx in range(first_index, len(days)):
        if a.update(left[idx]) != b.update(right[idx]):
            differences.append(days[idx])
    return differences


def audit(artifact: Path, audit_path: Path) -> dict:
    account = parse_archive_entry(artifact)
    days, closes, dividends = extract_closes_and_dividends(account)
    replacements = extract_disputes(audit_path, closes)
    changed_closes = dict(closes)
    changed_closes.update(replacements)
    left = exact_levels(days, closes, dividends)
    right = exact_levels(days, changed_closes, dividends)
    start = days.index(DISPUTED_DATES[0])
    require(all(left[i] == right[i] for i in range(start - 20, start)),
            "previous-20 start window has already diverged")
    variants = {}
    for label, model in (("h002", CloseChannel2010), ("h003", MeanReversion20)):
        for start_state in (False, True):
            key = f"{label}_initial_{'ON' if start_state else 'OFF'}"
            differences = different_state_days(days, left, right, start, model, start_state)
            variants[key] = dict(difference_days=len(differences),
                                 first_difference_dates=differences[:10])
    return dict(schema="dq001-signal-sensitivity.v1", status="DIAGNOSTIC_ONLY",
                evidence_run=ARCHIVE_RUN, evidence_artifact_id=ARCHIVE_ARTIFACT_ID,
                pinned_archived_buyhold_sha256=EXPECTED_BUYHOLD_SHA256,
                pinned_source_audit_sha256=EXPECTED_AUDIT_SHA256,
                derived_close_sessions=len(days), ex_dividend_events=len(dividends),
                disputed_quote_days=len(replacements), compared_session_start=days[start],
                compared_session_end=days[-1], compared_sessions=len(days) - start,
                test_states=["initial_ON", "initial_OFF"], sensitivity=variants,
                raw_ohlc_available=False, original_2019_warmup_available=False,
                historical_orders_replayed=False, performance_metrics=None,
                source_independence_certified=False, dq001_resolved=False,
                qualifying_h002_experiment=False, qualifying_h003_experiment=False,
                eligible_strategy_conclusions=0,
                caveat="Close-intent comparison only; no original open/high/low, no true fill/ledger replay; preserves all price disputes and the DQ001 blocking gate.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True,
                        help="Locally provided GitHub Actions run 39446205344 artifact ZIP")
    parser.add_argument("--output", type=Path,
                        help="NEW report path; never overwrite existing evidence")
    args = parser.parse_args(argv)
    try:
        report = audit(args.artifact, Path(__file__).resolve().parent / "results/DQ001_source_audit.json")
        encoded = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as f:
                f.write(encoded)
        else:
            print(encoded, end="")
    except (SensitivityInputError, OSError, KeyError) as exc:
        print(f"EVIDENCE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
