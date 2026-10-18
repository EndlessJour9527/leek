"""Dividend-aware ETF historical proxy. STRICTLY RESEARCH-ONLY.

Consumes provisional, explicitly sourced cash dividend events and secondary
raw price CSVs. Never claims vendor quality, corporate-action completeness,
tradeable fills, alpha, win rate, or broker readiness. Existing price_proxy
output is not rewritten.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path

from .ledger import Ledger, dec
from .price_proxy import ProxyBlocked, read_csv, git_blob_sha

D = Decimal


def _date(value: str) -> str:
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise ProxyBlocked("invalid ISO date") from exc
    return value


def _validate_events(payload: dict, bars: list) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {"version", "symbol", "coverage", "events"}:
        raise ProxyBlocked("invalid dividend evidence payload")
    if payload["version"] != "provisional-dividend.v1" or payload["symbol"] != "510300":
        raise ProxyBlocked("only provisional 510300 distribution research supported")
    if payload["coverage"] != "UNVERIFIED_SECONDARY_CROSSCHECK":
        raise ProxyBlocked("dividend feed has no approved completeness certificate")
    events = payload["events"]
    if not isinstance(events, list) or not events:
        raise ProxyBlocked("empty dividend feed")
    sessions = {b.day for b in bars}
    included = []
    all_ids = set()
    all_ex = set()
    all_record = set()
    all_pay = set()
    for event in events:
        expected = {"id", "published_on", "record_date", "ex_date", "pay_date",
                    "cash_per_share", "source_url", "source_grade"}
        if not isinstance(event, dict) or set(event) != expected:
            raise ProxyBlocked("invalid cash distribution fields")
        identifier = event["id"]
        if not isinstance(identifier, str) or not identifier.startswith("510300:") or identifier in all_ids:
            raise ProxyBlocked("duplicate/invalid dividend identifier")
        all_ids.add(identifier)
        pub, rec, ex, pay = (_date(event[key]) for key in
                              ("published_on", "record_date", "ex_date", "pay_date"))
        if not pub < rec < ex <= pay:
            raise ProxyBlocked("dividend event chronology invalid")
        if ex in all_ex:
            raise ProxyBlocked("overlapping ex-date unsupported")
        all_ex.add(ex)
        if rec in all_record or pay in all_pay:
            raise ProxyBlocked("overlapping record or pay date unsupported")
        all_record.add(rec)
        all_pay.add(pay)
        try:
            div = dec(event["cash_per_share"])
        except (ValueError, TypeError) as exc:
            raise ProxyBlocked("invalid dividend amount") from exc
        if div <= 0 or div >= D("100"):
            raise ProxyBlocked("out-of-range dividend amount")
        url = event["source_url"]
        if not isinstance(url, str) or not url.startswith("https://") or event["source_grade"] not in ("issuer_notice_mirrored", "secondary_dividend_schedule", "synthetic"):
            raise ProxyBlocked("dividend source missing")
        if rec in sessions or ex in sessions or pay in sessions:
            # Partial overlap is a hard failure, not a dividend silently skipped.
            if not {rec, ex, pay}.issubset(sessions):
                raise ProxyBlocked("dividend record/ex/pay session missing")
            included.append(dict(id=identifier, published_on=pub, record_date=rec,
                                 ex_date=ex, pay_date=pay, cash_per_share=div))
        elif bars[0].day <= ex <= bars[-1].day:
            raise ProxyBlocked("dividend trading session missing")
    return sorted(included, key=lambda x: (x["record_date"], x["id"]))


def _summary(nav, peak, min_drawdown, ledger, fills, rejected, completed, earned, eligible_events, portfolio):
    sym = "510300"
    p = ledger.positions[sym]
    return dict(
        total_nav_return_pct=round(float((nav / D("50000") - 1) * 100), 3),
        max_close_drawdown_pct=round(float(min_drawdown * 100), 3),
        terminal_nav_cny=round(float(nav), 2),
        cash_cny=round(float(ledger.cash), 2),
        dividend_receivable_cny=round(float(sum(ledger.receivables.values(), D(0))), 2),
        dividends_earned_cny=round(float(earned), 2),
        commission_cny=round(float(ledger.commission), 2),
        adverse_slippage_cny=round(float(ledger.slippage), 2),
        fill_count=fills,
        rejected_count=rejected,
        closed_round_trips=completed,
        closed_win_rate_pct=None,  # Attribution across ex/pay and lots is not qualified.
        open_qty=int(p["qty"]),
        position_cost_basis_cny=round(float(p["basis"]), 2),
        qualifying_event_count=len(eligible_events),
        portfolio=portfolio,
    )


def simulate(bars: list, events: list, confirmation: int, portfolio="trend") -> dict:
    """Signal: causal dividend-normalized TR level versus inclusive MA120.

    Cash distributions: after record-day close snapshot; at ex-day open accrue
    nonspendable receivable; at pay-day AFTER trading move receivable to cash.
    The signal's TR index credits ex-day per-share cash, not future payable cash.
    This does not convert the secondary raw-price input into a validated feed.
    """
    if confirmation not in (1, 3) or portfolio not in ("trend", "buy_hold"):
        raise ProxyBlocked("unregistered experiment variant")
    ledger = Ledger("50000", ["510300"])
    by_record = {e["record_date"]: e for e in events}
    by_ex = {e["ex_date"]: e for e in events}
    by_pay = {e["pay_date"]: e for e in events}
    state, up, down = False, 0, 0
    pending = None
    tr_history: list[D] = []
    prev_price = None
    last_nav, peak, max_dd = D("50000"), D("50000"), D(0)
    fills, rejected, completed = 0, 0, 0
    earned = D(0)
    eligible_events = []

    for i, bar in enumerate(bars):
        day = bar.day
        price_close, price_open = dec(str(bar.close)), dec(str(bar.open))
        div = by_ex[day]["cash_per_share"] if day in by_ex else D(0)
        # Ex occurs before market opens; quantity was snapshot at record close.
        if day in by_ex:
            evt = by_ex[day]
            ledger.ex("510300", evt["id"], div, "1", "exact")
            right = ledger.entitlements[("510300", evt["id"])]
            earned += right * div
            eligible_events.append(dict(ex_date=day, entitled_qty=str(right),
                                        cash_entitlement_cny=str(right * div)))
        if portfolio == "buy_hold" and i == 120:
            prev_close = dec(str(bars[119].close))
            q = (D("50000") * D("0.20") / prev_close // D("100")) * D("100")
            pending = ("BUY", q) if q else None
            if pending is None:
                raise ProxyBlocked("buy-hold benchmark cannot buy one board lot")
        if pending is not None:
            side, qty = pending
            px = price_open * (D("1.0005") if side == "BUY" else D("0.9995"))
            fee = max(D("5"), qty * px * D("0.0002"))
            try:
                ledger.fill("510300", side, qty, price_open, px, fee, day)
            except ValueError:
                rejected += 1
                if portfolio == "buy_hold":
                    raise ProxyBlocked("passive baseline failed to establish exposure")
            else:
                fills += 1
                if side == "SELL":
                    completed += 1
            pending = None
        if day in by_pay:
            evt = by_pay[day]
            ledger.pay("510300", evt["id"])
        nav = ledger.nav({"510300": price_close})
        peak = max(peak, nav)
        max_dd = min(max_dd, nav / peak - 1)
        last_nav = nav
        # Record date entitlement is determined by holdings after the day's
        # trading, independent of whether a payment arrives in the future.
        if day in by_record:
            ledger.record("510300", by_record[day]["id"])
        if prev_price is None:
            tr_history.append(D("1"))
        else:
            tr_history.append(tr_history[-1] * (price_close + div) / prev_price)
        prev_price = price_close
        if portfolio == "trend" and i >= 119:
            moving_average = sum(tr_history[-120:], D(0)) / D(120)
            current = tr_history[-1]
            if current > moving_average:
                up, down = up + 1, 0
            elif current < moving_average:
                down, up = down + 1, 0
            else:
                up = down = 0
            if up >= confirmation:
                state = True
            elif down >= confirmation:
                state = False
            if i + 1 < len(bars):
                qty = ledger.positions["510300"]["qty"]
                if state and qty == 0:
                    buy_qty = (nav * D("0.20") / price_close // D("100")) * D("100")
                    if buy_qty > 0:
                        pending = ("BUY", buy_qty)
                elif not state and qty > 0:
                    pending = ("SELL", qty)
    return _summary(last_nav, peak, max_dd, ledger, fills, rejected,
                    completed, earned, eligible_events, portfolio)


def compare(raw_price_csv: bytes, source: dict, evidence: dict) -> dict:
    if git_blob_sha(raw_price_csv) != source["blob_sha"]:
        raise ProxyBlocked("unmatched Git blob of market input")
    bars = read_csv(raw_price_csv)
    if (bars[0].day, bars[-1].day, len(bars)) != (source["first"], source["last"], source["count"]):
        raise ProxyBlocked("market sample boundary mismatch")
    events = _validate_events(evidence, bars)
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        result = {key: simulate(bars, events, confirmation, portfolio)
                  for key, confirmation, portfolio in (
                      ("buy_hold_20pct", 1, "buy_hold"),
                      ("ma120_1d", 1, "trend"),
                      ("h001_3d", 3, "trend"),
                  )}
    result["cash_0pct"] = {"total_nav_return_pct": 0, "max_close_drawdown_pct": 0,
                           "terminal_nav_cny": 50000}
    return dict(
        status="UNVALIDATED_CA_PROXY",
        explanation="Provisional dividend event crosscheck; not full original exchange-price or executable return validation.",
        source=source,
        input_sha256=hashlib.sha256(raw_price_csv).hexdigest(),
        dividends_sha256=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
        data_span=dict(from_date=bars[0].day,to_date=bars[-1].day,rows=len(bars)),
        events_used=[{"id":e["id"], "ex_date":e["ex_date"],
                      "cash_per_share":str(e["cash_per_share"])} for e in events],
        comparison=result,
        gates={
            "corporate_actions_complete":False,
            "verified_primary_ohlc":False,
            "verified_trade_execution":False,
            "out_of_sample_validated":False,
            "eligible_for_automatic_promotion":False,
        },
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    sources = json.loads(Path(args.sources).read_text())
    events = json.loads(Path(args.events).read_text())
    if args.source_id not in sources:
        ap.error("unknown source id")
    report = compare(Path(args.csv).read_bytes(), sources[args.source_id], events)
    out = Path(args.output)
    if out.exists():
        ap.error("refuse to overwrite existing report")
    out.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":report["status"],"from":report["data_span"]["from_date"],
                      "to":report["data_span"]["to_date"],"events":report["events_used"],
                      "comparison":report["comparison"]},sort_keys=True))


if __name__ == "__main__":
    main()
