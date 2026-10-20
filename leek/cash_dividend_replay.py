"""Synthetic cash-dividend portfolio replay; no taxes, splits or live data."""
import argparse
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from fractions import Fraction

from .contract import DataBlocked
from .ledger import Ledger, dec, valid_date
from .portfolio_replay import validate as validate_portfolio, VERSION as PORTFOLIO_VERSION
from .replay import (atomic_create, canonical, digest,
                     keys, load, source_hash, amount)

VERSION = 'synthetic-cash-dividend-replay.v1'
CA_POLICY = 'record-close.ex-before-open.pay-after-trading.gross-no-tax.v1'
POLICY = 'sells-first.priority-order.all-or-reject.v1'
MODEL = 'multi-instrument-forward-total-return.fixed-shares.v1'
D = Decimal
REJECTIONS = {
    'insufficient spendable cash': 'INSUFFICIENT_CASH',
    'insufficient settled shares': 'INSUFFICIENT_SETTLED_SHARES',
    'insufficient cash for sell commission': 'INSUFFICIENT_SELL_FEE_CASH',
}


def validate(config, data):
    """Validate all events before output; no inferred or default CA convention."""
    keys(config, 'version initial_cash quantities commission slippage_bps lookback symbol_priority execution_policy corporate_action_policy')
    keys(data, 'version synthetic instruments currency adjustment corporate_actions calendar bars')
    if config['version'] != VERSION or data['version'] != VERSION:
        raise DataBlocked('unsupported cash-dividend version')
    if config['corporate_action_policy'] != CA_POLICY:
        raise DataBlocked('unregistered corporate-action policy')
    plain_config = {k: v for k, v in config.items() if k != 'corporate_action_policy'}
    plain_config['version'] = PORTFOLIO_VERSION
    plain_data = dict(data, version=PORTFOLIO_VERSION, corporate_actions=[])
    validate_portfolio(plain_config, plain_data)
    events = data['corporate_actions']
    if not isinstance(events, list) or len(events) > 10000:
        raise DataBlocked('bounded corporate_actions list required')
    ids, ex_days = set(), set()
    calendar = data['calendar']
    for event in events:
        keys(event, 'event_id instrument kind published_on record_date ex_date pay_date cash_per_old_share split_ratio rounding')
        symbol, event_id = event['instrument'], event['event_id']
        if not isinstance(symbol, str) or symbol not in data['instruments']:
            raise DataBlocked('unknown corporate-action instrument')
        if (not isinstance(event_id, str) or not 1 <= len(event_id) <= 64
                or not event_id.isascii() or not event_id.isalnum()):
            raise DataBlocked('bounded alphanumeric corporate-action id required')
        key = (symbol, event_id)
        if key in ids:
            raise DataBlocked('duplicate corporate-action id')
        ids.add(key)
        if (event['kind'] != 'cash_dividend' or event['rounding'] != 'exact'
                or amount(event['split_ratio'], 'split_ratio', True) != 1):
            raise DataBlocked('only exact cash dividends; splits and rounding unsupported')
        dividend = amount(event['cash_per_old_share'], 'cash_per_old_share', True)
        try:
            for field in ('published_on', 'record_date', 'ex_date', 'pay_date'):
                valid_date(event[field])
        except (ValueError, TypeError) as exc:
            raise DataBlocked('invalid corporate-action date') from exc
        published, record, ex, pay = (event[k] for k in
            ('published_on', 'record_date', 'ex_date', 'pay_date'))
        if not published <= record < ex <= pay:
            raise DataBlocked('require published <= record < ex <= pay')
        if any(day not in calendar for day in (record, ex, pay)):
            raise DataBlocked('record/ex/pay must be covered by the explicit calendar')
        if (symbol, ex) in ex_days:
            raise DataBlocked('multiple same-symbol ex events unsupported')
        ex_days.add((symbol, ex))
        previous = dec(data['bars'][symbol][calendar.index(ex)-1]['close'])
        if dividend >= previous:
            raise DataBlocked('dividend must be below previous raw close')


def _fraction_text(value):
    return str(D(value.numerator) / D(value.denominator))


def _replay(config, data, count, binding):
    symbols = config['symbol_priority']
    ledger = Ledger(config['initial_cash'], symbols)
    realized = {s: D(0) for s in symbols}
    dividend_income = {s: D(0) for s in symbols}
    tr = {s: [] for s in symbols}
    events = sorted(data['corporate_actions'], key=lambda e: (e['record_date'], e['instrument'], e['event_id']))
    ca_log = []
    commissions = {s: D(0) for s in symbols}
    slippages = {s: D(0) for s in symbols}
    rows, signals, orders, pending, seen = [], [], [], [], set()
    rank = {s: i for i, s in enumerate(symbols)}
    for index in range(count):
        session = data['calendar'][index]
        ex_dividends = {s: D(0) for s in symbols}
        for event in events:
            if event['ex_date'] == session:
                symbol, event_id = event['instrument'], event['event_id']
                ledger.ex(symbol, event_id, event['cash_per_old_share'], '1', 'exact')
                income = ledger.receivables[(symbol, event_id)]
                dividend_income[symbol] += income
                ex_dividends[symbol] = dec(event['cash_per_old_share'])
                ca_log.append(dict(date=session, phase='ex_before_open', instrument=symbol,
                    event_id=event_id, amount=str(income)))
        # Deliberately release sale proceeds before cash allocation to buys.
        # Only configured rank, never input mapping order or future price,
        # breaks simultaneous-order ties. No partial fill or resizing.
        for intent in sorted(pending, key=lambda x: (x['side'] != 'SELL', rank[x['instrument']])):
            order = dict(intent)
            symbol, side = order['instrument'], order['side']
            if order['execute_on'] != session or order['event_id'] in seen:
                raise DataBlocked('invalid pending execution event')
            seen.add(order['event_id'])
            qty = dec(order['quantity'])
            raw = dec(data['bars'][symbol][index]['open'])
            slip = dec(config['slippage_bps']) / 10000
            price = raw * (1 + slip if side == 'BUY' else 1 - slip)
            fee = dec(config['commission'])
            before = ledger.positions[symbol]['basis']
            order.update(raw_open=str(raw), fill_price=str(price), commission=str(fee),
                         cash_before=str(ledger.cash))
            try:
                ledger.fill(symbol, side, qty, raw, price, fee, session)
            except ValueError as exc:
                # Programming/invariant failures must block, not look like a
                # normal funding rejection and permit a misleading report.
                if str(exc) not in REJECTIONS:
                    raise DataBlocked('unexpected ledger rejection') from exc
                order.update(status='rejected', reason=REJECTIONS[str(exc)],
                             filled_quantity='0', paid_commission='0', slippage='0')
            else:
                if side == 'SELL':
                    realized[symbol] += qty * price - fee - (before - ledger.positions[symbol]['basis'])
                cost = abs(price - raw) * qty
                commissions[symbol] += fee
                slippages[symbol] += cost
                order.update(status='filled', reason=None, filled_quantity=str(qty),
                             paid_commission=str(fee), slippage=str(cost))
            order['cash_after'] = str(ledger.cash)
            orders.append(order)
        pending = []
        closes = {s: dec(data['bars'][s][index]['close']) for s in symbols}
        for event in events:
            symbol, event_id = event['instrument'], event['event_id']
            if event['record_date'] == session:
                ledger.record(symbol, event_id)
                ca_log.append(dict(date=session, phase='record_close', instrument=symbol,
                    event_id=event_id, quantity=str(ledger.entitlements[(symbol, event_id)])))
        # Payment is after all trading, even when pay == ex. No same-day funding.
        for event in events:
            if event['pay_date'] == session:
                symbol, event_id = event['instrument'], event['event_id']
                paid = ledger.pay(symbol, event_id)
                ca_log.append(dict(date=session, phase='pay_after_trading', instrument=symbol,
                    event_id=event_id, amount=str(paid)))
        for symbol in symbols:
            # Exact rational comparisons avoid rounding creating false momentum
            # when raw prices return to an earlier level. Decimal is display only.
            close = Fraction(closes[symbol])
            level = close if index == 0 else tr[symbol][-1] * (
                close + Fraction(ex_dividends[symbol])) / Fraction(dec(data['bars'][symbol][index-1]['close']))
            tr[symbol].append(level)
        positions = {}
        for symbol in symbols:
            p = ledger.positions[symbol]
            market_value = p['qty'] * closes[symbol]
            unrealized = market_value - p['basis']
            receivable = sum((v for (s, _), v in ledger.receivables.items() if s == symbol), D(0))
            positions[symbol] = dict(quantity=str(p['qty']), basis=str(p['basis']),
                close=str(closes[symbol]), market_value=str(market_value),
                nav_contribution=str(market_value + receivable), receivable=str(receivable),
                dividend_income=str(dividend_income[symbol]), total_return_level=_fraction_text(tr[symbol][-1]),
                realized_pnl=str(realized[symbol]),
                unrealized_pnl=str(unrealized), total_pnl=str(realized[symbol] + unrealized + dividend_income[symbol]),
                commission=str(commissions[symbol]), slippage=str(slippages[symbol]))
        nav = ledger.nav(closes)
        realized_total = sum(realized.values(), D(0))
        unrealized_total = sum((dec(p['unrealized_pnl']) for p in positions.values()), D(0))
        income_total = sum(dividend_income.values(), D(0))
        if nav - dec(config['initial_cash']) != realized_total + unrealized_total + income_total:
            raise DataBlocked('portfolio accounting reconciliation failed')
        rows.append(dict(date=session, cash=str(ledger.cash), nav=str(nav), positions=positions,
                         receivables=str(sum(ledger.receivables.values(), D(0))), dividend_income=str(income_total),
                         realized_pnl=str(realized_total), unrealized_pnl=str(unrealized_total),
                         total_pnl=str(nav - dec(config['initial_cash'])),
                         commission=str(ledger.commission), slippage=str(ledger.slippage)))
        if index >= config['lookback']:
            next_session = data['calendar'][index + 1] if index + 1 < len(data['calendar']) else None
            for symbol in symbols:
                past = tr[symbol][index-config['lookback']]
                target = dec(config['quantities'][symbol]) if tr[symbol][index] > past else D(0)
                signals.append(dict(instrument=symbol, asof=session,
                    available_at=session + 'T23:59:59+00:00',
                    window_start=data['calendar'][index-config['lookback']],
                    target_quantity=str(target), execute_on=next_session))
                delta = target - ledger.positions[symbol]['qty']
                if delta:
                    side = 'BUY' if delta > 0 else 'SELL'
                    pending.append(dict(event_id=f'{symbol}:{session}:{side}', instrument=symbol,
                        signal_date=session, execute_on=next_session, side=side, quantity=str(abs(delta))))
    return dict(version=VERSION, binding=binding, processed_sessions=count,
                complete=count == len(data['calendar']), currency='SIM',
                instruments=symbols, execution_policy=POLICY, corporate_action_policy=CA_POLICY,
                corporate_action_log=ca_log, daily=rows,
                signals=signals, orders=orders, pending_orders=pending,
                processed_event_ids=sorted(seen))


def run(config_path, input_path, output_dir, resume=None, stop_after=None):
    """Write immutable report/checkpoint. Resume verifies a deterministic prefix.

    stop_after is the absolute session count. All input data must be unchanged.
    The entire prefix is re-executed; checkpoint state is never trusted.
    """
    config, config_hash = load(config_path)
    data, input_hash = load(input_path)
    validate(config, data)
    count = len(data['calendar']) if stop_after is None else stop_after
    if type(count) is not int or not 1 <= count <= len(data['calendar']):
        raise DataBlocked('stop_after outside input calendar')
    binding = dict(config_sha256=config_hash, input_sha256=input_hash,
                   source_sha256=source_hash(), model=MODEL,
                   execution_policy=POLICY, corporate_action_policy=CA_POLICY, decimal_precision=64)
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        if resume is not None:
            checkpoint, _ = load(resume)
            keys(checkpoint, 'version binding processed_sessions report report_sha256')
            if checkpoint['version'] != VERSION or checkpoint['binding'] != binding:
                raise DataBlocked('checkpoint version, source, config or input mismatch')
            prior_count = checkpoint['processed_sessions']
            if type(prior_count) is not int or not 1 <= prior_count <= count:
                raise DataBlocked('checkpoint progress mismatch')
            prior = _replay(config, data, prior_count, binding)
            if (checkpoint['report_sha256'] != digest(canonical(prior))
                    or canonical(checkpoint['report']) != canonical(prior)):
                raise DataBlocked('checkpoint integrity or replay mismatch')
        report = _replay(config, data, count, binding)
    output = Path(output_dir)
    output.mkdir(parents=False, exist_ok=False)
    checkpoint = dict(version=VERSION, binding=binding, processed_sessions=count,
                      report=report, report_sha256=digest(canonical(report)))
    atomic_create(output / 'checkpoint.json', checkpoint)
    atomic_create(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resume')
    parser.add_argument('--stop-after', type=int)
    args = parser.parse_args()
    try:
        report = run(args.config, args.input, args.output, args.resume, args.stop_after)
    except (ValueError, OSError, ArithmeticError) as exc:
        parser.exit(2, f'cash-dividend replay blocked: {exc}\n')
    print(f"processed={report['processed_sessions']} complete={report['complete']}")


if __name__ == '__main__':
    main()
