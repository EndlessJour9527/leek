"""Frozen E4 signal arithmetic. No downloads or historical runner."""
from decimal import Decimal as D, ROUND_FLOOR, ROUND_HALF_EVEN
from contract import DataBlocked
from ledger import dec

def shift_month(month, delta):
    y,m=map(int,month.split('-'))
    if m<1 or m>12:raise DataBlocked('invalid month')
    index=y*12+m-1+delta
    return f'{index//12:04d}-{index%12+1:02d}'

def momentum_scores(tr_month_ends, formation_month, start_lag, end_lag, symbols):
    start,end=shift_month(formation_month,-start_lag),shift_month(formation_month,-end_lag)
    out={}
    for s in symbols:
        try:a,b=dec(tr_month_ends[s][start]),dec(tr_month_ends[s][end])
        except (KeyError,ValueError,ArithmeticError):raise DataBlocked('missing momentum endpoint '+s)
        if a<=0 or b<=0:raise DataBlocked('invalid TR endpoint')
        out[s]=b/a-1
    return out

def ranked_symbols(scores, tolerance):
    tol=dec(tolerance)
    if tol<=0:raise ValueError('invalid tie quantum')
    return sorted(scores,key=lambda symbol:(-dec(scores[symbol]).quantize(tol,rounding=ROUND_HALF_EVEN),symbol))

def target_shares(weights, signal_nav, raw_closes, lot_size):
    nav,lot=dec(signal_nav),dec(lot_size)
    if nav<0 or lot<=0:raise ValueError('invalid target inputs')
    if sum(map(dec,weights.values()),D(0))>1 or any(dec(w)<0 for w in weights.values()):
        raise ValueError('invalid weights')
    out={}
    for s,w in weights.items():
        if s not in raw_closes or dec(raw_closes[s])<=0:raise DataBlocked('missing signal close '+s)
        out[s]=(dec(w)*nav/dec(raw_closes[s])/lot).to_integral_value(rounding=ROUND_FLOOR)*lot
    return out
