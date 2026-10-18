"""Research-only 510300 *price-path* diagnostic, NOT a qualified ETF backtest.

Uses externally supplied unadjusted secondary-source prices, with no dividend,
split, suspensions, order-book, live broker, or tax modelling. Deliberately
separate from leek.replay's strict synthetic-only contract. No research output
here may promote a strategy to validated or trigger an order.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path


class ProxyBlocked(ValueError):
    pass


@dataclass(frozen=True)
class Bar:
    day: str
    open: float
    close: float
    high: float
    low: float


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_csv(raw: bytes) -> list[Bar]:
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ProxyBlocked("UTF-8 CSV required") from exc
    reader = csv.DictReader(StringIO(decoded))
    if reader.fieldnames is None:
        raise ProxyBlocked("header missing")
    needed = {"日期", "高", "低"}
    if not needed.issubset(reader.fieldnames) or not (
        {"收盘", "开盘"}.issubset(reader.fieldnames)
        or {"收市", "開市"}.issubset(reader.fieldnames)
    ):
        raise ProxyBlocked("unsupported Chinese ETF CSV columns")
    rows = []
    for row in reader:
        if row.get(None):
            raise ProxyBlocked("malformed CSV row")
        try:
            raw_day = row["日期"]
            text_day = raw_day.replace("年", "-").replace("月", "-").replace("日", "")
            y, m, d = (int(v) for v in text_day.split("-"))
            day = date(y, m, d).isoformat()
            op = float(row.get("开盘", row.get("開市")))
            close = float(row.get("收盘", row.get("收市")))
            high, low = float(row["高"]), float(row["低"])
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            raise ProxyBlocked("invalid date or numeric CSV record") from exc
        import math
        if not all(math.isfinite(v) for v in (op, close, high, low)):
            raise ProxyBlocked("nonfinite price")
        if low <= 0 or high < max(op, close) or low > min(op, close):
            raise ProxyBlocked("invalid OHLC ordering")
        rows.append(Bar(day, op, close, high, low))
    rows.sort(key=lambda x: x.day)
    if len(rows) < 123:
        raise ProxyBlocked("insufficient observations for MA120 plus confirmation")
    if len({x.day for x in rows}) != len(rows):
        raise ProxyBlocked("duplicate session")
    if any(x.open <= 0 or x.close <= 0 for x in rows):
        raise ProxyBlocked("nonpositive price")
    return rows


def run_strategy(bars: list[Bar], confirmation: int, *,
                 initial_cash: float = 50000.0, budget: float = 0.2,
                 lot: int = 100, fee_rate: float = 0.0002, min_fee: float = 5.0,
                 slippage: float = 0.0005) -> dict:
    """Signal at completed close t; fixed whole-lot intent; fill at open t+1.

    No lookahead, dividend processing, liquidation of last-position, or
    tradeability guarantee. Returns price-proxy stats only.
    """
    if confirmation not in (1, 3):
        raise ProxyBlocked("only registered baseline or H001 allowed")
    cash, qty, basis, buy_index = initial_cash, 0, 0.0, -1
    peak, min_dd, roll_sum = initial_cash, 0.0, 0.0
    state, up, down, pending = False, 0, 0, None
    wins = losses = complete = filled = rejected = 0
    costs = realized = 0.0
    daily = []
    for i, bar in enumerate(bars):
        if pending is not None:
            side, amount = pending
            price = bar.open * (1 + slippage if side == "BUY" else 1 - slippage)
            value = amount * price
            fee = max(min_fee, fee_rate * value)
            if side == "BUY" and qty == 0 and cash >= value + fee:
                cash -= value + fee
                qty += amount
                basis += value + fee
                buy_index = i
                costs += fee
                filled += 1
            elif side == "SELL" and qty >= amount and buy_index < i:
                cash += value - fee
                qty -= amount
                pnl = value - fee - basis
                realized += pnl
                complete += 1
                wins += pnl > 0
                losses += pnl < 0
                basis = 0
                costs += fee
                filled += 1
            else:
                rejected += 1
            pending = None
        nav = cash + qty * bar.close
        peak = max(peak, nav)
        min_dd = min(min_dd, nav / peak - 1)
        daily.append((bar.day, nav))
        roll_sum += bar.close
        if i >= 120:
            roll_sum -= bars[i - 120].close
        if i >= 119:
            moving_average = roll_sum / 120
            if bar.close > moving_average:
                up += 1
                down = 0
            elif bar.close < moving_average:
                down += 1
                up = 0
            else:
                up = down = 0
            if up >= confirmation:
                state = True
            elif down >= confirmation:
                state = False
            if i + 1 < len(bars):
                if state and qty == 0:
                    intended_qty = (int((nav * budget / bar.close) // lot)) * lot
                    if intended_qty > 0:
                        pending = ("BUY", intended_qty)
                elif not state and qty:
                    pending = ("SELL", qty)
    return dict(
        total_return_pct=round(100 * (daily[-1][1] / initial_cash - 1), 3),
        max_close_drawdown_pct=round(100 * min_dd, 3),
        terminal_nav=round(daily[-1][1], 2),
        closed_trades=complete, winning_trades=wins, losing_trades=losses,
        closed_trade_win_rate_pct=round(100 * wins / complete, 2) if complete else None,
        fill_events=filled, rejected_events=rejected, commission_paid=round(costs, 2),
        open_position_qty=qty,
        realized_pnl=round(realized, 2),
        unrealized_pnl=round(qty * bars[-1].close - basis, 2),
    )



def buy_hold_20pct_price_proxy(bars: list[Bar]) -> dict:
    """Cash-funded one-time 20% buy at first executable post-warmup open.

    Uses previous session close to size the intention. No terminal liquidation,
    dividends, exit costs, or position rebalancing; not a risk-adjusted alpha
    comparator. The benchmark is itself UNVALIDATED_PRICE_PROXY.
    """
    capital, budget, lot = 50000.0, 0.2, 100
    cash, qty, peak, min_dd = capital, 0, capital, 0.0
    fee_paid = 0.0
    if len(bars) < 121:
        raise ProxyBlocked("benchmark warmup missing")
    target = int((capital * budget / bars[119].close) // lot) * lot
    if target <= 0:
        raise ProxyBlocked("buy-and-hold unable to reach minimum trading unit")
    first_open = bars[120].open * (1.0 + 0.0005)
    fee_paid = max(5.0, target * first_open * 0.0002)
    if target * first_open + fee_paid > cash:
        raise ProxyBlocked("buy-and-hold initial fill unaffordable")
    for i, bar in enumerate(bars):
        if i == 120:
            qty = target
            cash -= target * first_open + fee_paid
        nav = cash + qty * bar.close
        peak = max(peak, nav)
        min_dd = min(min_dd, nav / peak - 1)
    return dict(
        total_return_pct=round((nav / capital - 1) * 100, 3),
        max_close_drawdown_pct=round(100 * min_dd, 3),
        terminal_nav=round(nav, 2),
        open_position_qty=qty, commission_paid=round(fee_paid, 2),
        note="one-time 20% entry after 120-session warmup; terminal exit cost not deducted",
    )

def run_diagnostic(raw: bytes, source: dict) -> dict:
    for field in ("repository", "path", "commit", "blob_sha", "first", "last", "count"):
        if field not in source:
            raise ProxyBlocked("incomplete pinned source manifest")
    if git_blob_sha(raw) != source["blob_sha"]:
        raise ProxyBlocked("source blob checksum mismatch")
    bars = read_csv(raw)
    if (len(bars), bars[0].day, bars[-1].day) != (source["count"], source["first"], source["last"]):
        raise ProxyBlocked("manifest period or count mismatch")
    return {
        "status": "UNVALIDATED_PRICE_PROXY",
        "note": "Not an ETF total-return or executable-trade backtest; do not promote.",
        "source": source, "sha256": hashlib.sha256(raw).hexdigest(),
        "sessions": len(bars), "from": bars[0].day, "to": bars[-1].day,
        "assumptions": {
            "initial_cash_cny": 50000, "entry_budget_fraction": 0.2,
            "lot_size": 100, "signal": "close vs inclusive MA120; 1d/3d confirmation",
            "fill": "next observed session unadjusted open", "slippage_per_fill_bps": 5,
            "commission_fraction_per_fill": 0.0002, "minimum_commission_cny": 5,
            "exit": "next open after confirmed signal; no forced terminal liquidation",
            "unsupported": ["cash_dividend", "split", "delisting", "suspension",
                            "limit_up_down", "order_book", "spread_outside_slippage",
                            "taxes", "exchange_calendar_verification"],
        },
        "cash_0pct": {"total_return_pct": 0.0, "max_close_drawdown_pct": 0.0, "terminal_nav": 50000.0},
        "buy_hold_20pct": buy_hold_20pct_price_proxy(bars),
        "baseline_ma120_1d": run_strategy(bars, 1),
        "challenger_h001_3d": run_strategy(bars, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    if args.source_id not in manifest:
        ap.error("source-id not found in manifest")
    report = run_diagnostic(Path(args.csv).read_bytes(), manifest[args.source_id])
    output = Path(args.output)
    if output.exists():
        ap.error("output exists; refusing overwrite")
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "sessions", "from", "to", "cash_0pct", "buy_hold_20pct", "baseline_ma120_1d", "challenger_h001_3d")},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
