"""Strategy-free shared-cash ledger. Decimal arithmetic; no market-data defaults."""
from decimal import Decimal, ROUND_CEILING, getcontext

getcontext().prec = max(getcontext().prec, 50)
D = Decimal

def dec(value):
    value = D(str(value))
    if not value.is_finite():
        raise ValueError('nonfinite amount')
    return value

class Ledger:
    def __init__(self, cash, symbols):
        self.cash = dec(cash)
        if self.cash < 0 or len(symbols) != len(set(symbols)):
            raise ValueError('invalid initial state')
        self.positions = {s: {'qty': D(0), 'basis': D(0), 'lots': []} for s in symbols}
        self.entitlements = {}
        self.receivables = {}
        self.ex_applied = set()
        self.paid = set()
        self.commission = D(0)
        self.slippage = D(0)

    def record(self, symbol, event_id):
        key = (symbol, event_id)
        if key in self.entitlements:
            raise ValueError('duplicate record')
        self.entitlements[key] = self.positions[symbol]['qty']

    def ex(self, symbol, event_id, cash_per_old_share, split_ratio, rounding):
        key = (symbol, event_id)
        div, ratio = dec(cash_per_old_share), dec(split_ratio)
        if rounding not in ('exact', 'ceil_whole_account'):
            raise ValueError('unregistered share rounding')
        if key in self.ex_applied or key not in self.entitlements or div < 0 or ratio <= 0:
            raise ValueError('invalid or duplicate ex event')
        self.receivables[key] = self.entitlements[key] * div
        p = self.positions[symbol]
        theoretical_qty = p['qty'] * ratio
        p['qty'] = theoretical_qty.to_integral_value(rounding=ROUND_CEILING) if rounding == 'ceil_whole_account' else theoretical_qty
        p['lots'] = [(d, n * ratio) for d, n in p['lots']]
        # Assign the rounding increment to the latest acquired lot conservatively.
        if p['qty'] != theoretical_qty:
            latest = max(range(len(p['lots'])), key=lambda i: p['lots'][i][0])
            d, n = p['lots'][latest]
            p['lots'][latest] = (d, n + p['qty'] - theoretical_qty)
        self.ex_applied.add(key)

    def pay(self, symbol, event_id):
        key = (symbol, event_id)
        if key in self.paid or key not in self.receivables:
            raise ValueError('unearned or duplicate payment')
        amount = self.receivables.pop(key)
        self.cash += amount
        self.paid.add(key)
        return amount

    def sellable(self, symbol, date):
        return sum((n for d, n in self.positions[symbol]['lots'] if d < date), D(0))

    def fill(self, symbol, side, qty, raw_open, fill_price, commission, date):
        n, raw, px, fee = map(dec, (qty, raw_open, fill_price, commission))
        if side not in ('BUY', 'SELL') or n <= 0 or raw <= 0 or px <= 0 or fee < 0:
            raise ValueError('invalid fill')
        if (side == 'BUY' and px < raw) or (side == 'SELL' and px > raw):
            raise ValueError('beneficial slippage is outside this model')
        p = self.positions[symbol]
        value = n * px
        if side == 'BUY':
            if value + fee > self.cash:
                raise ValueError('insufficient spendable cash')
            self.cash -= value + fee
            p['qty'] += n
            p['basis'] += value + fee
            p['lots'].append((date, n))
        else:
            if n > self.sellable(symbol, date):
                raise ValueError('insufficient settled shares')
            if self.cash + value - fee < 0:
                raise ValueError('insufficient cash for sell commission')
            p['basis'] *= (p['qty'] - n) / p['qty']
            p['qty'] -= n
            remaining = n
            lots = []
            for bought, amount in p['lots']:
                take = min(remaining, amount) if bought < date else D(0)
                remaining -= take
                if amount > take:
                    lots.append((bought, amount - take))
            p['lots'] = lots
            self.cash += value - fee
        self.commission += fee
        self.slippage += abs(px - raw) * n  # Reporting only; already embedded in fill price.

    def nav(self, closes):
        value = self.cash + sum(self.receivables.values(), D(0))
        for symbol, p in self.positions.items():
            if p['qty']:
                if symbol not in closes:
                    raise ValueError('missing valuation close: ' + symbol)
                close = dec(closes[symbol])
                if close <= 0:
                    raise ValueError('invalid valuation close')
                value += p['qty'] * close
        return value
