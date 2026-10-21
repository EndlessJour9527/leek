"""In-memory path assembly. There is deliberately no CLI running real histories.
A separate frozen data qualification and independent G1 authorization are required.
"""
from decimal import Decimal as D
from contract import DataBlocked,require_pool
from portfolio import PortfolioEngine
from schedule import build_schedule

def run_path(panel,sessions,events,registry,strategy,cost,window,qualification,release=None):
    if qualification.get('fixture_kind')!='HAND_AUTHORED_SYNTHETIC':
        from release_gate import VerifiedRelease
        if not isinstance(release,VerifiedRelease):raise DataBlocked('independent hash-bound release is required')
        if qualification!=release.qualification:raise DataBlocked('qualification differs from signed release')
        release.validate_inputs(panel,sessions,events,window,registry)
    if strategy not in registry['strategies'] or cost not in registry['cost_scenarios']:
        raise DataBlocked('strategy/cost not exactly registered')
    if set(panel)!=set(registry['universe']):raise DataBlocked('fixed pool mismatch')
    schedule,ends=build_schedule(sessions,window['initial_signal'],window['initial_formation'],window['start'],window['end'],strategy)
    engine=PortfolioEngine(registry['universe'],registry['initial_cash_cny'],events,cost,100,qualification['odd_lot_exit_allowed'])
    for date in sessions:
        if date>window['end']:break
        quotes={}
        for s in registry['universe']:
            if date not in panel[s]:raise DataBlocked('missing panel/status row '+s+' '+date)
            quotes[s]=panel[s][date]
        entry=schedule.get(date);decision=entry['decision'] if entry else None
        if decision and decision['kind'] in ('buy_hold','cash'):
            decision={'kind':'fixed','weights':{s:(D(str(decision['weight'])) if decision['kind']=='buy_hold' and s==decision['symbol'] else D(0)) for s in registry['universe']}}
        engine.step(date,quotes,decision,entry['next_session'] if entry else None,date in ends.values(),date>=window['start'])
    return engine
