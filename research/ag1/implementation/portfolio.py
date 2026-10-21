"""Causal multi-asset session orchestration. Normalized evidence is mandatory.
No raw-data adapter or historical performance command is enabled yet.
"""
import copy
from datetime import datetime
from decimal import Decimal as D, ROUND_HALF_EVEN
from ledger import Ledger,dec
from ca_math import transformed_reference,chain_total_return
from contract import DataBlocked,validate_calendar,validate_raw_bar
from monthly_signals import momentum_scores,ranked_symbols,target_shares
from execution import OrderExecutor,make_plan,transform_plan
from cash_gate import gate_on


def timestamp(value):
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None:raise DataBlocked('timezone required for known_at')
    return stamp


class PortfolioEngine:
    def __init__(self, symbols, capital, events, cost, lot_size, odd_lot_exit_allowed):
        self.symbols=sorted(symbols)
        self.ledger=Ledger(capital,self.symbols)
        self.initial_cash=dec(capital);self.events=copy.deepcopy(events);self.cost=cost
        self.lot=dec(lot_size);self.odd=odd_lot_exit_allowed
        self.executor=OrderExecutor();self.pending=None;self.marks={};self.tr={}
        self.monthly={s:{} for s in self.symbols};self.applied=[]
        self.daily=[];self.signals=[];self.executions=[];self.event_log=[];self.previous_date=None
        ids=set()
        for e in self.events:
            key=(e['symbol'],e['id'])
            if key in ids:raise DataBlocked('duplicate event')
            ids.add(key)
            if e['status']=='cancelled':continue
            if e['status']!='implemented':raise DataBlocked('unresolved event')
            if e['phase'] not in ('before_open','after_close'):raise DataBlocked('unknown event phase')
            if e['record_date']>e['effective_date'] or (e['record_date']==e['effective_date'] and e['phase']=='before_open'):
                raise DataBlocked('invalid event record timing')
            if e['pay_date'] and e['pay_date']<e['effective_date']:raise DataBlocked('invalid event pay timing')
            timestamp(e['known_at'])

    def _known(self, when, purpose):
        for e in self.applied:
            if timestamp(e['known_at'])>timestamp(when):
                raise DataBlocked('event factor unavailable for '+purpose+': '+e['id'])

    def _apply(self,e,date,phase):
        s=e['symbol'];ratio=dec(e['ratio']);div=dec(e['cash_per_old_share'])
        old_qty=self.ledger.positions[s]['qty'];old_mark=self.marks.get(s)
        self.ledger.ex(s,e['id'],div,ratio,e['rounding'])
        new_mark=transformed_reference(old_mark,div,ratio) if old_mark is not None else None
        rounding_qty=self.ledger.positions[s]['qty']-old_qty*ratio
        self.event_log.append(dict(date=date,phase=phase,event_id=e['id'],symbol=s,
                                   type='effective',ratio=ratio,rounding_quantity=rounding_qty,
                                   rounding_nav_delta=rounding_qty*new_mark if new_mark is not None else D(0)))
        if self.pending:
            affected=any(o['symbol']==s for o in self.pending['orders'])
            if affected and ratio!=1:
                execution_time=self.pending['execution_date']+'T09:30:00+08:00'
                if timestamp(e['known_at'])>timestamp(execution_time):
                    raise DataBlocked('pending plan conversion factor unavailable: '+e['id'])
                transform_plan(self.pending,s,ratio,self.lot)
        self.applied.append(e)
        return new_mark

    def step(self,date,quotes,decision=None,next_session=None,month_end=False,active=True):
        # A blocked day must not leave a half-mutated account that can be resumed.
        state_names=('ledger','executor','pending','marks','tr','monthly','applied','previous_date')
        state={name:copy.deepcopy(getattr(self,name)) for name in state_names}
        sizes={name:len(getattr(self,name)) for name in ('daily','signals','executions','event_log')}
        try:
            return self._step(date,quotes,decision,next_session,month_end,active)
        except Exception:
            for name,value in state.items():setattr(self,name,value)
            for name,size in sizes.items():del getattr(self,name)[size:]
            raise

    def _step(self,date,quotes,decision=None,next_session=None,month_end=False,active=True):
        if self.previous_date and date<=self.previous_date:raise DataBlocked('non-increasing session')
        if set(quotes)!=set(self.symbols):raise DataBlocked('fixed pool missing quote/status row')
        for s,q in quotes.items():
            if q.get('status')=='suspended_verified':
                if not q.get('suspension_evidence') or s not in self.marks:raise DataBlocked('unverified or unmarkable suspension')
            else:
                if q.get('status') not in ('trading_verified','observed_daily_conditional'):raise DataBlocked('unqualified trading status '+s)
                if q.get('status')=='observed_daily_conditional' and q.get('conditional_policy')!='CLARIFICATION_004':raise DataBlocked('unqualified conditional status '+s)
                validate_raw_bar(dict(q,date=date))
        effective=[e for e in self.events if e['status']=='implemented' and e['effective_date']==date]
        if len({e['symbol'] for e in effective})!=len(effective):raise DataBlocked('same-day actions must be explicitly consolidated')
        factors={s:(D(0),D(1)) for s in self.symbols}
        stale_marks=dict(self.marks)
        for e in effective:
            if e['phase']=='before_open':
                stale_marks[e['symbol']]=self._apply(e,date,'before_open')
                factors[e['symbol']]=(dec(e['cash_per_old_share']),dec(e['ratio']))
        if self.pending:
            if self.pending['execution_date']!=date:raise DataBlocked('pending plan calendar mismatch')
            self.executions.append(self.executor.execute(self.ledger,self.pending,quotes,date,self.cost,self.lot))
            self.pending=None
        close_marks={};stale={}
        for s,q in quotes.items():
            stale[s]=q['status']=='suspended_verified'
            close=stale_marks[s] if stale[s] else dec(q['close'])
            close_marks[s]=close
            div,ratio=factors[s]
            self.tr[s]=chain_total_return(self.tr[s],self.marks[s],close,div,ratio) if s in self.tr else D(100)
        self.marks=close_marks
        close_nav=self.ledger.nav(self.marks)
        for e in self.events:
            if e['status']=='implemented' and e['record_date']==date:
                self.ledger.record(e['symbol'],e['id'])
                self.event_log.append(dict(date=date,phase='close',type='record',event_id=e['id'],symbol=e['symbol']))
        if month_end:
            for s in self.symbols:self.monthly[s][date[:7]]=self.tr[s]
        if decision is not None:
            if next_session is None:
                self.signals.append(dict(date=date,status='no_next_session_no_order',strategy=decision['kind']))
            else:
                self._known(date+'T15:00:00+08:00','signal')
                kind=decision['kind'];scores={};ranking=[]
                if kind=='momentum':
                    scores=momentum_scores(self.monthly,decision['formation_month'],decision['start_lag'],1,self.symbols)
                    ranking=ranked_symbols(scores,'0.000000000001')
                    chosen=ranking[:decision['top_k']]
                    weights={s:dec(decision['selected_weight']) if s in chosen else D(0) for s in self.symbols}
                    if decision.get('absolute_cash_gate') and not gate_on(scores,self.symbols):
                        weights={s:D(0) for s in self.symbols}
                elif kind=='fixed':weights={s:dec(decision['weights'][s]) for s in self.symbols}
                else:raise ValueError('unregistered decision kind')
                targets=target_shares(weights,close_nav,self.marks,self.lot)
                self.pending=make_plan(date,date,next_session,weights,targets,self.marks,close_nav,self.ledger.positions,self.lot,self.odd)
                self.signals.append(dict(date=date,status='planned',strategy=kind,scores=scores,
                                         quantized_scores={s:v.quantize(D('0.000000000001'),rounding=ROUND_HALF_EVEN) for s,v in scores.items()},
                                         ranking=ranking,stale=copy.deepcopy(stale),plan=copy.deepcopy(self.pending)))
        for e in effective:
            if e['phase']=='after_close':
                self.marks[e['symbol']]=self._apply(e,date,'after_close')
        for e in self.events:
            if e['status']=='implemented' and e['pay_date']==date:
                amount=self.ledger.pay(e['symbol'],e['id'])
                self.event_log.append(dict(date=date,phase='after_close',type='payment',event_id=e['id'],symbol=e['symbol'],amount=amount))
        nav=self.ledger.nav(self.marks)
        if active:
            self.daily.append(dict(date=date,nav=nav,close_before_afterclose_actions_nav=close_nav,
                                   cash=self.ledger.cash,receivable=sum(self.ledger.receivables.values(),D(0)),
                                   positions=copy.deepcopy(self.ledger.positions),marks=dict(self.marks),
                                   tr=dict(self.tr),stale=stale,commission=self.ledger.commission,slippage=self.ledger.slippage))
        self.previous_date=date
        return self.daily[-1] if active else None


def segment(rows,start,end,initial_cash):
    selected=[r for r in rows if start<=r['date']<=end]
    if not selected:raise ValueError('empty segment')
    prior=[r for r in rows if r['date']<start]
    base=prior[-1]['nav'] if prior else dec(initial_cash)
    return {'starting_nav':base,'ending_nav':selected[-1]['nav'],'return_fraction':selected[-1]['nav']/base-1,'account_reset':False}
