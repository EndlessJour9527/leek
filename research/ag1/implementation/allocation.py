"""Exact common-scalar lot allocation per frozen clarification 001."""
from decimal import Decimal as D, ROUND_FLOOR
from fractions import Fraction
from ledger import dec

def commission(notional, rate, minimum):
    notional,rate,minimum=map(dec,(notional,rate,minimum))
    if min(notional,rate,minimum)<0:raise ValueError('negative fee input')
    return max(minimum,notional*rate) if notional else D(0)

def capped_buy_quantity(planned_quantity, signal_planned_notional, signal_weight_budget, fill_price, lot_size):
    planned,nominal,budget,px,lot=map(dec,(planned_quantity,signal_planned_notional,signal_weight_budget,fill_price,lot_size))
    if min(planned,nominal,budget)<0 or min(px,lot)<=0:raise ValueError('invalid buy cap')
    return (min(planned,nominal/px,budget/px)/lot).to_integral_value(rounding=ROUND_FLOOR)*lot

def common_scalar_allocation(quantities, fill_prices, cash, lot_size, commission_rate, minimum_commission):
    lot,cash=dec(lot_size),dec(cash)
    rate,minimum=dec(commission_rate),dec(minimum_commission)
    if lot<=0 or min(cash,rate,minimum)<0:raise ValueError('invalid allocation input')
    codes=sorted(quantities)
    lots={s:int(dec(quantities[s])/lot) for s in codes}
    if any(dec(quantities[s])<0 or dec(quantities[s])!=lots[s]*lot for s in codes):
        raise ValueError('quantities must be nonnegative whole lots')
    px={s:dec(fill_prices[s]) for s in codes}
    if any(v<=0 for v in px.values()):raise ValueError('invalid fill price')
    # Each step is a reachable vector floor(alpha * demand_lots), not a greedy fill.
    boundaries=sorted({Fraction(0),Fraction(1)}|{Fraction(j,n) for n in lots.values() for j in range(1,n+1)})
    best={s:D(0) for s in codes};best_cost=D(0);left=Fraction(0);right=Fraction(1);right_closed=True
    for alpha in boundaries:
        vector={s:D((alpha.numerator*lots[s])//alpha.denominator)*lot for s in codes}
        cost=sum((vector[s]*px[s]+commission(vector[s]*px[s],rate,minimum) for s in codes),D(0))
        if cost>cash:
            right=alpha;right_closed=False
            break
        if vector != best or alpha == 0:
            best,best_cost,left=vector,cost,alpha
    return {'quantities':best,'total_cost':best_cost,'cash_remaining':cash-best_cost,
            'alpha_interval':{'left':str(left),'left_closed':True,'right':str(right),'right_closed':right_closed},
            'remainder_reallocated':False}
