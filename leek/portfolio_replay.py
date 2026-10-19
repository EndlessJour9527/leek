"""Synthetic-only shared-cash replay; independent of the single-symbol CLI."""
import argparse
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from .contract import DataBlocked
from .ledger import Ledger, dec
from .replay import (VERSION as SINGLE_VERSION, atomic_create, canonical, digest,
                     keys, load, source_hash, validate as validate_single)

VERSION = 'synthetic-portfolio-replay.v1'
POLICY = 'sells-first.priority-order.all-or-reject.v1'
MODEL = 'multi-instrument-close-momentum.fixed-shares.v1'
D = Decimal
REJECTIONS = {
    'insufficient spendable cash': 'INSUFFICIENT_CASH',
    'insufficient settled shares': 'INSUFFICIENT_SETTLED_SHARES',
    'insufficient cash for sell commission': 'INSUFFICIENT_SELL_FEE_CASH',
}


def validate(config, data):
    """Validate the entire fixed universe before creating state or output."""
    keys(config, 'version initial_cash quantities commission slippage_bps lookback symbol_priority execution_policy')
    keys(data, 'version synthetic instruments currency adjustment corporate_actions calendar bars')
    if config['version'] != VERSION or data['version'] != VERSION:
        raise DataBlocked('unsupported portfolio version')
    if config['execution_policy'] != POLICY:
        raise DataBlocked('unregistered execution policy')
    symbols = data['instruments']
    if (not isinstance(symbols, list) or not 2 <= len(symbols) <= 64
            or any(not isinstance(s, str) or not 1 <= len(s) <= 32
                   or not s.isascii() or not s.isalnum() for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise DataBlocked('2 to 64 unique ASCII alphanumeric instruments required')
    priority = config['symbol_priority']
    if (not isinstance(priority, list) or any(not isinstance(s, str) for s in priority)
            or len(priority) != len(symbols) or set(priority) != set(symbols)):
        raise DataBlocked('priority must be an explicit permutation of instruments')
    for name, value in [('quantities', config['quantities']), ('bars', data['bars'])]:
        if not isinstance(value, dict) or set(value) != set(symbols):
            raise DataBlocked(name + ': fixed universe mismatch')
    for symbol in symbols:
        single_config = {k: config[k] for k in ('initial_cash', 'commission', 'slippage_bps', 'lookback')}
        single_config.update(version=SINGLE_VERSION, quantity=config['quantities'][symbol])
        single_data = {k: data[k] for k in ('synthetic', 'currency', 'adjustment', 'corporate_actions', 'calendar')}
        single_data.update(version=SINGLE_VERSION, instrument=symbol, bars=data['bars'][symbol])
        validate_single(single_config, single_data)


def _replay(config, data, count, binding):
    symbols = config['symbol_priority']
    ledger = Ledger(config['initial_cash'], symbols)
    realized = {s: D(0) for s in symbols}
    commissions = {s: D(0) for s in symbols}
    slippages = {s: D(0) for s in symbols}
    rows, signals, orders, pending, seen = [], [], [], [], set()
    rank = {s: i for i, s in enumerate(symbols)}
    for index in range(count):
        session = data['calendar'][index]
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
                    realized[symbol] += qty * price - fee - before
                cost = abs(price - raw) * qty
                commissions[symbol] += fee
                slippages[symbol] += cost
                order.update(status='filled', reason=None, filled_quantity=str(qty),
                             paid_commission=str(fee), slippage=str(cost))
            order['cash_after'] = str(ledger.cash)
            orders.append(order)
        pending = []
        closes = {s: dec(data['bars'][s][index]['close']) for s in symbols}
        positions = {}
        for symbol in symbols:
            p = ledger.positions[symbol]
            market_value = p['qty'] * closes[symbol]
            unrealized = market_value - p['basis']
            positions[symbol] = dict(quantity=str(p['qty']), basis=str(p['basis']),
                close=str(closes[symbol]), market_value=str(market_value),
                nav_contribution=str(market_value), realized_pnl=str(realized[symbol]),
                unrealized_pnl=str(unrealized), total_pnl=str(realized[symbol] + unrealized),
                commission=str(commissions[symbol]), slippage=str(slippages[symbol]))
        nav = ledger.nav(closes)
        realized_total = sum(realized.values(), D(0))
        unrealized_total = sum((dec(p['unrealized_pnl']) for p in positions.values()), D(0))
        if nav - dec(config['initial_cash']) != realized_total + unrealized_total:
            raise DataBlocked('portfolio accounting reconciliation failed')
        rows.append(dict(date=session, cash=str(ledger.cash), nav=str(nav), positions=positions,
                         realized_pnl=str(realized_total), unrealized_pnl=str(unrealized_total),
                         total_pnl=str(nav - dec(config['initial_cash'])),
                         commission=str(ledger.commission), slippage=str(ledger.slippage)))
        if index >= config['lookback']:
            next_session = data['calendar'][index + 1] if index + 1 < len(data['calendar']) else None
            for symbol in symbols:
                past = dec(data['bars'][symbol][index-config['lookback']]['close'])
                target = dec(config['quantities'][symbol]) if closes[symbol] > past else D(0)
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
                instruments=symbols, execution_policy=POLICY, daily=rows,
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
                   execution_policy=POLICY, decimal_precision=64)
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
        parser.exit(2, f'portfolio replay blocked: {exc}\n')
    print(f"processed={report['processed_sessions']} complete={report['complete']}")


if __name__ == '__main__':
    main()
