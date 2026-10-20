"""Deterministic, synthetic-only, single-instrument offline replay.

No broker, network, exchange calendar inference, or corporate-action handling.
A checkpoint is an integrity-checked replay prefix, never trusted executable state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .contract import DataBlocked, validate_calendar, validate_raw_bar
from .ledger import Ledger, dec

VERSION = 'synthetic-replay.v1'
D = Decimal


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_hash():
    """Bind recovery to all Python implementation files in this package."""
    root = Path(__file__).parent
    return digest(canonical({p.name: digest(p.read_bytes()) for p in sorted(root.glob('*.py'))}))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataBlocked('duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path):
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(DataBlocked('nonfinite JSON')))
    except (ValueError, UnicodeError) as exc:
        raise DataBlocked('invalid JSON: ' + str(path)) from exc
    return value, digest(raw)


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise DataBlocked('unexpected or missing fields; expected: ' + expected)


def amount(value, name, positive=False):
    if not isinstance(value, str) or len(value) > 40:
        raise DataBlocked(name + ' must be a bounded decimal string')
    try:
        number = dec(value)
        if number < 0 or (positive and number == 0) or number > D('1e12') or not -12 <= number.as_tuple().exponent <= 12:
            raise ValueError()
    except ValueError as exc:
        raise DataBlocked('invalid ' + name) from exc
    return number


def validate(config, data):
    keys(config, 'version initial_cash quantity commission slippage_bps lookback')
    if config['version'] != VERSION:
        raise DataBlocked('unsupported configuration version')
    for field in ('initial_cash', 'quantity', 'commission', 'slippage_bps'):
        amount(config[field], field, field in ('initial_cash', 'quantity'))
    if dec(config['quantity']) != dec(config['quantity']).to_integral_value():
        raise DataBlocked('whole-share quantity required')
    if dec(config['slippage_bps']) >= 10000:
        raise DataBlocked('slippage must be below 10000 bps')
    if type(config['lookback']) is not int or not 1 <= config['lookback'] <= 10000:
        raise DataBlocked('lookback must be an integer in [1, 10000]')
    keys(data, 'version synthetic instrument currency adjustment corporate_actions calendar bars')
    if data['version'] != VERSION or data['synthetic'] is not True:
        raise DataBlocked('only explicitly synthetic v1 data is supported')
    if data['adjustment'] != 'raw' or data['corporate_actions'] != []:
        raise DataBlocked('corporate actions and adjusted bars are unsupported')
    if not isinstance(data['instrument'], str) or not data['instrument'].isascii() or not data['instrument'].isalnum():
        raise DataBlocked('ASCII alphanumeric instrument required')
    if data['currency'] != 'SIM':
        raise DataBlocked('synthetic SIM currency required')
    if not isinstance(data['calendar'], list) or not isinstance(data['bars'], list):
        raise DataBlocked('calendar and bars must be lists')
    if any(not isinstance(session, str) for session in data['calendar']):
        raise DataBlocked('calendar dates must be strings')
    validate_calendar(data['calendar'])
    if len(data['bars']) != len(data['calendar']):
        raise DataBlocked('exactly one bar per explicit session required')
    for session, bar in zip(data['calendar'], data['bars']):
        keys(bar, 'date open high low close')
        if bar['date'] != session:
            raise DataBlocked('bar order or calendar coverage mismatch')
        for field in ('open', 'high', 'low', 'close'):
            amount(bar[field], field, True)
        validate_raw_bar(bar)


def atomic_create(path, value):
    """Publish one complete file exclusively via same-filesystem hard link.

    Temporary bytes are fsynced before publication. Existing destinations are
    never overwritten. Local filesystems supporting hard links are required.
    """
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)  # Atomic no-clobber publication, including races.
    finally:
        os.unlink(temp)


def _replay(config, data, count, binding):
    """Process the prefix; execution sees open only, signal sees closes <= t."""
    symbol = data['instrument']
    ledger = Ledger(config['initial_cash'], [symbol])
    rows, signals, orders, seen = [], [], [], set()
    pending = None
    realized = D(0)
    for index in range(count):
        bar = data['bars'][index]
        session = data['calendar'][index]
        if pending is not None:
            if pending['execute_on'] != session:
                raise DataBlocked('pending order calendar mismatch')
            order = dict(pending)
            event_id = order['event_id']
            if event_id in seen:
                raise DataBlocked('duplicate execution event')
            seen.add(event_id)
            qty = dec(order['quantity'])
            raw = dec(bar['open'])
            slip = dec(config['slippage_bps']) / 10000
            price = raw * (1 + slip if order['side'] == 'BUY' else 1 - slip)
            fee = dec(config['commission'])
            position = ledger.positions[symbol]
            basis_before = position['basis']
            order.update(raw_open=str(raw), fill_price=str(price), commission=str(fee))
            try:
                ledger.fill(symbol, order['side'], qty, raw, price, fee, session)
            except ValueError as exc:
                order.update(status='rejected', reason=str(exc), filled_quantity='0', paid_commission='0', slippage='0')
            else:
                if order['side'] == 'SELL':
                    # Fixed-size entries and all-or-nothing fills mean every
                    # sell closes the whole position; no average-cost division.
                    realized += qty * price - fee - basis_before
                order.update(status='filled', filled_quantity=str(qty), paid_commission=str(fee),
                             slippage=str(abs(price - raw) * qty))
            orders.append(order)
            pending = None
        position = ledger.positions[symbol]
        close = dec(bar['close'])
        market_value = position['qty'] * close
        nav = ledger.nav({symbol: close})
        unrealized = market_value - position['basis']
        if nav - dec(config['initial_cash']) != realized + unrealized:
            # Decimal rounding may affect average cost division; this strategy
            # only enters/exits whole positions, so equality must be exact.
            raise DataBlocked('accounting reconciliation failed')
        rows.append(dict(date=session, cash=str(ledger.cash), quantity=str(position['qty']),
                         basis=str(position['basis']), close=str(close), market_value=str(market_value),
                         nav=str(nav), realized_pnl=str(realized), unrealized_pnl=str(unrealized),
                         total_pnl=str(nav - dec(config['initial_cash'])),
                         commission=str(ledger.commission), slippage=str(ledger.slippage)))
        if index >= config['lookback']:
            target = dec(config['quantity']) if close > dec(data['bars'][index-config['lookback']]['close']) else D(0)
            next_session = data['calendar'][index+1] if index+1 < len(data['calendar']) else None
            signal = dict(asof=session, available_at=session + 'T23:59:59+00:00',
                          window_start=data['calendar'][index-config['lookback']],
                          target_quantity=str(target), execute_on=next_session)
            signals.append(signal)
            delta = target - position['qty']
            if delta:
                side = 'BUY' if delta > 0 else 'SELL'
                pending = dict(event_id=f'{symbol}:{session}:{side}', instrument=symbol,
                               signal_date=session, execute_on=next_session, side=side, quantity=str(abs(delta)))
    return dict(version=VERSION, binding=binding, processed_sessions=count,
                complete=count == len(data['calendar']), instrument=symbol, currency='SIM',
                daily=rows, signals=signals, orders=orders, pending_order=pending,
                processed_event_ids=sorted(seen))


def run(config_path, input_path, output_dir, resume=None, stop_after=None):
    """Run a prefix or all sessions into a NEW directory.

    stop_after is the absolute number of sessions, not an incremental count.
    Resume replays and verifies the saved prefix, then continues deterministically.
    The old run and checkpoint remain immutable; resume needs a new output path.
    """
    config, config_hash = load(config_path)
    data, input_hash = load(input_path)
    validate(config, data)
    count = len(data['calendar']) if stop_after is None else stop_after
    if type(count) is not int or not 1 <= count <= len(data['calendar']):
        raise DataBlocked('stop_after outside input calendar')
    binding = dict(config_sha256=config_hash, input_sha256=input_hash,
                   source_sha256=source_hash(), model='single-instrument-close-momentum.fixed-shares.v1',
                   decimal_precision=64)
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
            if checkpoint['report_sha256'] != digest(canonical(prior)) or canonical(checkpoint['report']) != canonical(prior):
                raise DataBlocked('checkpoint integrity or replay mismatch')
        report = _replay(config, data, count, binding)
    output = Path(output_dir)
    output.mkdir(parents=False, exist_ok=False)
    checkpoint = dict(version=VERSION, binding=binding, processed_sessions=count,
                      report=report, report_sha256=digest(canonical(report)))
    # A crash between these writes leaves a valid checkpoint for a NEW output
    # directory; it never causes a partially written file or an implicit retry.
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
        parser.exit(2, f'replay blocked: {exc}\n')
    print(f"processed={report['processed_sessions']} complete={report['complete']}")


if __name__ == '__main__':
    main()
