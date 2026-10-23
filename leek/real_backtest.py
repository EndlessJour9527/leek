"""Real historical daily-bar research, not brokerage execution.

Raw open fills plus adverse tick rounding are modelling assumptions. Inputs are
retrieved historical vendor versions, not certified point-in-time archives.
No synthetic fallback, broker connection, optimizer or automatic promotion.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from fractions import Fraction
import json
from pathlib import Path

from .contract import DataBlocked, validate_calendar
from .channel_signal import CloseChannel2010, MODEL_ID as H002
from .mean_reversion_signal import MeanReversion20, MODEL_ID as H003
from .history_data import VERSION, validate_bars
from .ledger import Ledger, dec
from .replay import atomic_create, canonical, digest, load, source_hash

D=Decimal
STRATEGIES=('cash','buy_hold','ma120_1d','h001_3d')
REJECTIONS={'insufficient spendable cash','insufficient settled shares','insufficient cash for sell commission'}


def checked_config(c):
    if c.get('version')!='real-history-research.v1' or c.get('instrument')!='510300':
        raise DataBlocked('unsupported research configuration')
    if c.get('lookback')!=120 or type(c.get('lot_size')) is not int or c['lot_size']!=100:
        raise DataBlocked('MA120 and 100-share research lot are frozen')
    if tuple(c.get('strategies',[]))!=STRATEGIES or set(c.get('cost_cases',{}))!={'base','stress'}:
        raise DataBlocked('registered comparison variants required')
    if c.get('tick_size')!='0.001' or not 0<dec(c['entry_budget_fraction'])<=1 or dec(c['initial_cash'])<=0:
        raise DataBlocked('invalid account/tick configuration')
    for k in ('warmup_start','evaluation_start','evaluation_end'):
        if date.fromisoformat(c[k]).isoformat()!=c[k]: raise DataBlocked('noncanonical date')
    if not c['warmup_start']<c['evaluation_start']<c['evaluation_end']:
        raise DataBlocked('invalid evaluation window')
    for case in c['cost_cases'].values():
        if set(case)!={'commission_rate','minimum_commission','slippage_bps'}:
            raise DataBlocked('unknown cost fields')
        if not 0<=dec(case['commission_rate'])<1 or not 0<=dec(case['minimum_commission']):
            raise DataBlocked('invalid commission')
        if not 0<=dec(case['slippage_bps'])<10000: raise DataBlocked('invalid slippage')


def checked_events(events,bars):
    days=[b['date'] for b in bars]; lookup={d:i for i,d in enumerate(days)}
    ids=set(); exdates=set()
    for event in events:
        if set(event)!={'event_id','record_date','ex_date','pay_date','cash_per_share','source_url'}:
            raise DataBlocked('unknown distribution fields or unsupported action')
        if not isinstance(event['event_id'],str) or not event['event_id'] or event['event_id'] in ids:
            raise DataBlocked('duplicate/missing event identity')
        ids.add(event['event_id'])
        r,e,p=(event[k] for k in ('record_date','ex_date','pay_date'))
        if not r<e<=p or any(d not in lookup for d in (r,e,p)) or e in exdates:
            raise DataBlocked('distribution chronology/calendar mismatch')
        exdates.add(e)
        cash=dec(event['cash_per_share'])
        if not 0<cash<dec(bars[lookup[e]-1]['close']): raise DataBlocked('invalid dividend')
        if not isinstance(event['source_url'],str) or not event['source_url'].startswith('https://'):
            raise DataBlocked('event source required')


def _price(raw,side,case,tick):
    slip=dec(case['slippage_bps'])/10000
    exact=raw*(1+slip if side=='BUY' else 1-slip)
    rounded=(exact/tick).to_integral_value(rounding=ROUND_CEILING if side=='BUY' else ROUND_FLOOR)*tick
    if rounded<=0: raise DataBlocked('nonpositive slippage-adjusted price')
    return rounded


def _fee(q,px,case):
    return max(dec(case['minimum_commission']),q*px*dec(case['commission_rate'])).quantize(D('.01'),rounding=ROUND_HALF_UP)


def _new_quantity(cash,nav,close,config,case):
    lot=D(config['lot_size']); tick=dec(config['tick_size'])
    budget=min(cash,nav*dec(config['entry_budget_fraction']))
    px=_price(close,'BUY',case,tick)
    q=max(D(0),((budget-dec(case['minimum_commission']))/(px*(1+dec(case['commission_rate'])))/lot).to_integral_value(rounding=ROUND_FLOOR)*lot)
    while q and q*px+_fee(q,px,case)>budget: q-=lot
    return q


def simulate(bars,events,config,strategy,case):
    """Pure model. Test fixtures may call this; the file CLI requires real data."""
    checked_config(config); validate_bars(bars); checked_events(events,bars)
    if strategy not in STRATEGIES + (H002,H003): raise DataBlocked('unknown strategy')
    start=config['evaluation_start']; end=config['evaluation_end']
    first=next((i for i,b in enumerate(bars) if b['date']>=start),None)
    if first is None or first<config['lookback']+2 or bars[-1]['date']>end:
        raise DataBlocked('insufficient warmup or invalid terminal boundary')
    ledger=Ledger(config['initial_cash'],['510300']); capital=dec(config['initial_cash'])
    tick=dec(config['tick_size']); grouped={field:defaultdict(list) for field in ('record_date','ex_date','pay_date')}
    for event in events:
        for field in grouped: grouped[field][event[field]].append(event)
    levels=[]; rolling=Fraction(0); up=down=0; state=False
    confirmations=3 if strategy=='h001_3d' else 1
    channel=CloseChannel2010() if strategy==H002 else None
    reversion=MeanReversion20() if strategy==H003 else None
    pending=None; active=None; cycles=[]; rights_cycle={}; realized=D(0); income=D(0)
    daily=[]; orders=[]; ca_log=[]; signals=[]; has_bought=False
    nav=capital; peak=capital; worst=D(0); year_start=capital; last_year=None; annual={}
    exposure_sum=D(0); seen=set()
    for i,bar in enumerate(bars):
        day=bar['date']; opening=dec(bar['open']); close=dec(bar['close'])
        dividend=D(0)
        for event in grouped['ex_date'][day]:
            eid=event['event_id']; cash=dec(event['cash_per_share']); dividend+=cash
            ledger.ex('510300',eid,cash,'1','exact')
            earned=ledger.receivables[('510300',eid)]; income+=earned
            cycle_id=rights_cycle[eid]
            if earned:
                if cycle_id is None: raise DataBlocked('unattributed dividend entitlement')
                cycles[cycle_id]['income']+=earned
            ca_log.append(dict(date=day,phase='ex',event_id=eid,amount=str(earned),cycle_id=cycle_id))
        if pending is not None:
            intent=dict(pending); pending=None
            if intent['execute_on']!=day or intent['signal_date']>=day or intent['id'] in seen:
                raise DataBlocked('invalid/duplicate intent timing')
            seen.add(intent['id']); side=intent['side']; q=dec(intent['quantity'])
            px=_price(opening,side,case,tick); fee=_fee(q,px,case)
            before=ledger.positions['510300']['basis']; cash_before=ledger.cash
            try:
                ledger.fill('510300',side,q,opening,px,fee,day)
            except ValueError as exc:
                if str(exc) not in REJECTIONS: raise DataBlocked('unexpected ledger error') from exc
                intent.update(status='rejected',reason=str(exc),commission='0',slippage='0')
            else:
                if side=='BUY':
                    if active is not None: raise DataBlocked('unexpected overlapping entry')
                    active=len(cycles); has_bought=True
                    cycles.append(dict(id=active,entry_date=day,quantity=q,entry_cost=q*px+fee,
                                       exit_date=None,exit_proceeds=D(0),income=D(0)))
                else:
                    if active is None or ledger.positions['510300']['qty']!=0:
                        raise DataBlocked('expected complete single-cycle exit')
                    realized+=q*px-fee-(before-ledger.positions['510300']['basis'])
                    cycles[active].update(exit_date=day,exit_proceeds=q*px-fee); active=None
                intent.update(status='filled',reason=None,commission=str(fee),
                              slippage=str(abs(px-opening)*q))
            intent.update(fill_price=str(px),cash_before=str(cash_before),cash_after=str(ledger.cash))
            orders.append(intent)
        for event in grouped['record_date'][day]:
            eid=event['event_id']; ledger.record('510300',eid); rights_cycle[eid]=active
            ca_log.append(dict(date=day,phase='record',event_id=eid,
                              quantity=str(ledger.entitlements[('510300',eid)]),cycle_id=active))
        for event in grouped['pay_date'][day]:
            paid=ledger.pay('510300',event['event_id'])
            ca_log.append(dict(date=day,phase='pay',event_id=event['event_id'],amount=str(paid)))
        nav=ledger.nav({'510300':close}); position=ledger.positions['510300']
        unrealized=position['qty']*close-position['basis']
        if nav-capital != realized+unrealized+income: raise DataBlocked('NAV/PnL reconciliation failed')
        if ledger.cash<0: raise DataBlocked('negative cash')
        level=Fraction(close) if not levels else levels[-1]*(Fraction(close)+Fraction(dividend))/Fraction(dec(bars[i-1]['close']))
        levels.append(level); rolling+=level
        if i>=config['lookback']: rolling-=levels[i-config['lookback']]
        if i>=config['lookback']-1:
            average=rolling/config['lookback']
            if level>average: up+=1; down=0
            elif level<average: down+=1; up=0
            else: up=down=0
            if up>=confirmations: state=True
            elif down>=confirmations: state=False
        if channel is not None:
            state=channel.update(level)
        if reversion is not None:
            state=reversion.update(level)
        if i>=first:
            peak=max(peak,nav); worst=min(worst,nav/peak-1)
            exposure=position['qty']*close/nav; exposure_sum+=exposure
            year=day[:4]
            if last_year is not None and year!=last_year:
                year_start=dec(daily[-1]['nav'])
            annual[year]=str((nav/year_start-1)*100); last_year=year
            daily.append(dict(date=day,nav=str(nav),cash=str(ledger.cash),quantity=str(position['qty']),
                market_value=str(position['qty']*close),receivables=str(sum(ledger.receivables.values(),D(0))),
                realized_trading_pnl=str(realized),unrealized_trading_pnl=str(unrealized),
                dividend_income=str(income),commission=str(ledger.commission),slippage=str(ledger.slippage),
                drawdown=str(nav/peak-1),exposure=str(exposure)))
        # The final pre-start close may register the first evaluation-day order.
        if i>=first-1:
            side=None; q=D(0); qty=position['qty']
            target_on = strategy=='buy_hold' or (strategy in ('ma120_1d','h001_3d',H002,H003) and state)
            if target_on and not qty and not (strategy=='buy_hold' and has_bought):
                q=_new_quantity(ledger.cash,nav,close,config,case); side='BUY'
            elif strategy in ('ma120_1d','h001_3d',H002,H003) and not state and qty:
                q=qty; side='SELL'
            next_day=bars[i+1]['date'] if i+1<len(bars) else None
            signals.append(dict(asof=day,available_at=day+'T17:00:00+08:00',
                                state='ON' if target_on else 'OFF',execute_on=next_day))
            if side and q:
                pending=dict(id=day+':'+side,signal_date=day,execute_on=next_day,side=side,quantity=str(q))
    closed=[]; open_cycles=[]
    for cycle in cycles:
        c=dict(cycle)
        if c['exit_date'] is not None:
            c['net_pnl']=c['exit_proceeds']-c['entry_cost']+c['income']; closed.append(c)
        else:
            c['marked_net_pnl']=c['quantity']*dec(bars[-1]['close'])-c['entry_cost']+c['income']; open_cycles.append(c)
    reconciled=sum((c['net_pnl'] for c in closed),D(0))+sum((c['marked_net_pnl'] for c in open_cycles),D(0))
    if nav-capital!=reconciled: raise DataBlocked('cycle attribution reconciliation failed')
    wins=[c['net_pnl'] for c in closed if c['net_pnl']>0]; losses=[c['net_pnl'] for c in closed if c['net_pnl']<0]
    years=(date.fromisoformat(bars[-1]['date'])-date.fromisoformat(bars[first-1]['date'])).days/365.25
    def number(v): return round(float(v),6)
    summary=dict(strategy=strategy,first_tradeable_date=bars[first]['date'],last_date=bars[-1]['date'],
        evaluated_sessions=len(daily),terminal_nav=number(nav),total_return_pct=number((nav/capital-1)*100),
        annualized_return_pct=100*((float(nav/capital)**(1/years))-1),max_close_drawdown_pct=number(worst*100),
        mean_exposure_pct=number(100*exposure_sum/len(daily)),commission=number(ledger.commission),
        slippage=number(ledger.slippage),dividend_income=number(income),closed_trades=len(closed),
        wins=len(wins),losses=len(losses),closed_win_rate_pct=100*len(wins)/len(closed) if closed else None,
        mean_closed_net_pnl=number(sum((c['net_pnl'] for c in closed),D(0))/len(closed)) if closed else None,
        average_net_win=number(sum(wins)/len(wins)) if wins else None,
        average_net_loss=number(sum(losses)/len(losses)) if losses else None,
        profit_factor=number(sum(wins)/abs(sum(losses))) if losses else None,
        open_cycles=len(open_cycles),filled_orders=sum(o['status']=='filled' for o in orders),
        rejected_orders=sum(o['status']=='rejected' for o in orders),
        annual_returns_pct={y:number(v) for y,v in annual.items()},
        evidence='RETROSPECTIVE_REAL_DATA_CONDITIONAL_BACKTEST',automatic_promotion=False)
    def texts(c): return {k:str(v) if isinstance(v,D) else v for k,v in c.items()}
    return dict(summary=summary,daily=daily,orders=orders,signals=signals,
                closed_trades=[texts(c) for c in closed],open_trades=[texts(c) for c in open_cycles],
                corporate_action_log=ca_log,terminal_intent=pending)


def run(input_path,config_path,output):
    data,data_hash=load(input_path); config,config_hash=load(config_path); checked_config(config)
    if data.get('version')!=VERSION or data.get('synthetic') is not False or data.get('adjustment')!='raw' or data.get('instrument')!='510300':
        raise DataBlocked('real unadjusted 510300 dataset required')
    if data['calendar']!=[b['date'] for b in data['bars']]: raise DataBlocked('calendar mismatch')
    if data['metadata'].get('config_sha256')!=config_hash: raise DataBlocked('data/config binding mismatch')
    if data['metadata'].get('crosscheck',{}).get('differing_cells')!=0:
        raise DataBlocked('historical data did not pass crosscheck')
    results={}
    with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
        for cost_name,cost in config['cost_cases'].items():
            for strategy in config['strategies']:
                results[cost_name+'__'+strategy]=simulate(data['bars'],data['dividends'],config,strategy,cost)
    directory=Path(output); directory.mkdir(parents=True,exist_ok=False)
    binding=dict(input_sha256=data_hash,config_sha256=config_hash,source_sha256=source_hash())
    summary=dict(status='COMPLETED_CONDITIONAL_REAL_HISTORY',binding=binding,
                 audit=data['metadata'],frozen_protocol=config,
                 results={key:value['summary'] for key,value in results.items()},
                 disclaimer='Developmental historical experiment; no untouched holdout, execution certification or broker approval.')
    for key,value in results.items():
        atomic_create(directory/(key+'.json'),dict(binding=binding,**value))
    atomic_create(directory/'summary.json',summary)
    print(json.dumps({'BACKTEST_SUMMARY':summary},sort_keys=True))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True); p.add_argument('--config',default='research/real_history_protocol.json'); p.add_argument('--output',required=True)
    a=p.parse_args(); run(a.input,a.config,a.output)

if __name__=='__main__': main()