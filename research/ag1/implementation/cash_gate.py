from decimal import Decimal as D
from contract import DataBlocked

def gate_on(scores,symbols):
    if set(scores)!=set(symbols):raise DataBlocked('incomplete gate scores')
    values=[D(str(scores[s])) for s in symbols]
    if not values or any(not v.is_finite() for v in values):raise DataBlocked('invalid gate scores')
    return max(values)>0
