"""Causal equal-weight risk signal from supplied total-return levels."""
import math
from decimal import Decimal as D
from .contract import DataBlocked, iso_date
from .ledger import dec

LOOKBACK=60
CAP=D('0.95')
TARGET=D('0.10')

def estimate(values):
    if len(values)!=LOOKBACK:raise DataBlocked('exactly 60 returns required')
    try:
        x=[float(v) for v in values]
    except (ValueError, TypeError, OverflowError) as exc:
        raise DataBlocked("invalid risk return") from exc
    if any(not math.isfinite(v) for v in x):raise DataBlocked('nonfinite risk return')
    if any(v <= -1 or abs(v) > 1e100 for v in x):
        raise DataBlocked("risk return outside numerical domain")
    mean=math.fsum(x)/LOOKBACK
    variance=math.fsum((v-mean)**2 for v in x)/(LOOKBACK-1)
    sigma=math.sqrt(252*variance)
    exposure=0.95 if sigma==0 else min(0.95,0.10/sigma)
    return repr(sigma),repr(exposure)

class RiskState:
    def __init__(self,symbols):
        symbols = tuple(symbols)
        if not symbols or len(symbols) != len(set(symbols)):
            raise DataBlocked("nonempty unique risk symbols required")
        self.symbols=sorted(symbols);self.prior=None;self.returns=[];self.dates=[]
    def update(self,date,tr):
        iso_date(date)
        if self.dates and date<=self.dates[-1]:raise DataBlocked('non-increasing risk session')
        if set(tr)!=set(self.symbols):raise DataBlocked('risk fixed pool mismatch')
        try:
            current={s:dec(tr[s]) for s in self.symbols}
        except ValueError as exc:
            raise DataBlocked("invalid TR point") from exc
        if any(not v.is_finite() or v<=0 for v in current.values()):raise DataBlocked('invalid TR point')
        if self.prior is not None:
            self.returns.append(sum((current[s]/self.prior[s]-1 for s in self.symbols),D(0))/D(len(self.symbols)))
        self.prior=current;self.dates.append(date)
    def signal(self):
        if len(self.returns)<LOOKBACK:raise DataBlocked('insufficient risk warmup')
        sigma,exposure=estimate(self.returns[-LOOKBACK:])
        return dict(signal_date=self.dates[-1],return_window_start=self.dates[-LOOKBACK],tr_base_date=self.dates[-LOOKBACK-1],return_window_end=self.dates[-1],observations=LOOKBACK,sigma=sigma,exposure=exposure)
