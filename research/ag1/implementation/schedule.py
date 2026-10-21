"""Registered monthly scheduling from an exchange calendar, never observed bars."""
from contract import DataBlocked,validate_calendar

def month_ends_from_calendar(sessions):
    validate_calendar(sessions)
    # Last supplied session is not presumed month-end; requires next-month evidence.
    return {a[:7]:a for a,b in zip(sessions,sessions[1:]) if a[:7]!=b[:7]}

def build_schedule(sessions,initial_signal,initial_formation,start,end,strategy):
    validate_calendar(sessions)
    if initial_signal not in sessions or start not in sessions or end not in sessions:
        raise DataBlocked('window outside qualified calendar')
    idx=sessions.index(initial_signal)
    if idx+1>=len(sessions) or sessions[idx+1]!=start:
        raise DataBlocked('initial signal is not immediately before execution start')
    ends=month_ends_from_calendar(sessions)
    signals={initial_signal:initial_formation}
    if strategy['kind'] not in ('buy_hold_no_dividend_reinvestment','cash'):
        signals.update({d:month for month,d in ends.items() if initial_signal<d<=end})
    out={}
    for d,formation in sorted(signals.items()):
        kind=strategy['kind']
        if kind=='cross_sectional_total_return_momentum':
            decision=dict(kind='momentum',formation_month=formation,start_lag=strategy['formation_month_lag_start'],top_k=strategy['top_k'],selected_weight=strategy['selected_weight'])
            if strategy['formation_month_lag_end']!=1:raise DataBlocked('unsupported momentum endpoint')
        elif kind=='monthly_static_equal_weight':decision=dict(kind='fixed',weights=strategy['weights'])
        elif kind=='buy_hold_no_dividend_reinvestment':decision=dict(kind='buy_hold',symbol=strategy['symbol'],weight=strategy['initial_weight'])
        elif kind=='cash':decision=dict(kind='cash')
        else:raise DataBlocked('unknown registered strategy')
        next_idx=sessions.index(d)+1
        following=sessions[next_idx] if next_idx<len(sessions) and sessions[next_idx]<=end else None
        out[d]={'decision':decision,'next_session':following}
    return out,ends
