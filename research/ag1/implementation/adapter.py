"""Read-only input normalization. No strategy, ranking or return calculation.
This adapter never creates a data-release approval and cannot run histories.
"""
import hashlib,json
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_UP
from contract import DataBlocked,validate_calendar,validate_raw_bar
from ledger import dec

def read_json(path):return json.loads(Path(path).read_text(),parse_float=str)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def normalized_cash_events(paths,end):
    out=[];seen=set()
    for path in paths:
        for e in read_json(path):
            if e['symbol'] not in ('510300','510500','512100','159915') or e['ex_date']>end:continue
            if e['cash_fields_verified'] is not True:raise DataBlocked('unverified cash fields')
            if e['event_id'] in seen:raise DataBlocked('duplicate cash event')
            seen.add(e['event_id'])
            if not Path(e['source_path']).is_file() or sha(e['source_path'])!=e['source_sha256']:raise DataBlocked('cash source changed')
            if 'cash_per_10_shares_cny' not in e:raise DataBlocked('original distribution unit missing')
            # Reconstruct exact official per-ten-share units; do not import binary-float artifacts.
            amount=dec(e['cash_per_10_shares_cny'])/10
            out.append(dict(id=e['event_id'],symbol=e['symbol'],status='implemented',record_date=e['record_date'],
                            effective_date=e['ex_date'],phase='before_open',pay_date=e['pay_date'],cash_per_old_share=str(amount),
                            ratio='1',rounding='exact',known_at=e['signal_available_from'],
                            evidence=[{'path':e['source_path'],'sha256':e['source_sha256']}],original_cash_per_10_shares=str(e['cash_per_10_shares_cny'])))
    return out

def normalized_share_events(path,end):
    out=[]
    for e in read_json(path):
        if e['status']=='CANCELLED_DO_NOT_APPLY':
            out.append(dict(id=e['event_id'],symbol=e['symbol'],status='cancelled',evidence=e['evidence']));continue
        if e['status']!='IMPLEMENTED':raise DataBlocked('share action status unresolved')
        if e['legal_effective_date']>end:continue
        known=e.get('exact_ratio_known_at')
        if not known:raise DataBlocked('exact ratio known_at missing: '+e['event_id'])
        if e['cash_in_lieu_to_account'] is not False:raise DataBlocked('unsupported cash-in-lieu needs explicit account rule')
        phase={'AFTER_CLOSE':'after_close','NONTRADING_ACTION_DAY':'before_open','BEFORE_OPEN':'before_open'}.get(e['legal_effective_phase'])
        if not phase:raise DataBlocked('unknown share event phase')
        out.append(dict(id=e['event_id'],symbol=e['symbol'],status='implemented',record_date=e['record_date'],
                        effective_date=e['legal_effective_date'],phase=phase,pay_date=None,cash_per_old_share='0',
                        ratio=e['account_new_shares_per_old_share'],rounding=e['account_rounding'],known_at=known,evidence=e['evidence']))
    return out

def limit_prices(reference,rate,tick):
    reference,rate,tick=map(dec,(reference,rate,tick))
    if min(reference,tick)<=0 or not 0<rate<1:raise DataBlocked('invalid price-limit metadata')
    return ((reference*(1-rate)/tick).to_integral_value(rounding=ROUND_HALF_UP)*tick,
            (reference*(1+rate)/tick).to_integral_value(rounding=ROUND_HALF_UP)*tick)

def normalize_panel(data_root,registry,events,window):
    from ca_math import transformed_reference
    from schedule import build_schedule
    data_root=Path(data_root)
    sessions=read_json(data_root/'panel/expected_sessions.json')
    validate_calendar(sessions)
    rules=read_json(data_root/'trading_rules/historical_regimes_v2.json')
    status_rows=read_json(data_root/'panel/session_status.json')
    status={(r['symbol'],r['date']):r for r in status_rows}
    if len(status)!=len(status_rows):raise DataBlocked('duplicate status row')
    executions=set()
    for strategy in registry['strategies']:
        schedule,_=build_schedule(sessions,window['initial_signal'],window['initial_formation'],window['start'],window['end'],strategy)
        executions.update(v['next_session'] for v in schedule.values() if v['next_session'])
    share_events=read_json(data_root/'share_action_events_v2.json')
    unverified_reference={(e['symbol'],e['first_post_action_quote_date']) for e in share_events if e['status']=='IMPLEMENTED'}
    if any(d in executions for _,d in unverified_reference):raise DataBlocked('unverified corporate-action reference on registered execution date')
    panel={};exception_report=[];source_pins={}
    def pin(path,expected=None):
        path=Path(path)
        key=str(path.resolve())
        if key in source_pins:
            if expected and source_pins[key]!=expected:raise DataBlocked('conflicting source hash')
            return
        if not path.is_file():raise DataBlocked('missing source '+str(path))
        actual=sha(path)
        if expected and actual!=expected:raise DataBlocked('source changed '+str(path))
        source_pins[str(path.resolve())]=actual
    for p in (data_root/'panel/expected_sessions.json',data_root/'panel/session_status.json',data_root/'trading_rules/historical_regimes_v2.json',data_root/'share_action_events_v2.json'):
        pin(p)
    for r in rules['regimes']:
        for entry in (r['source'],r.get('special_20pct_source')):
            if entry:pin(data_root/'trading_rules'/entry['file'],entry['sha256'])
    for entry in rules['effective_sources']+rules['tax']['stamp_sources']+[rules['tax']['distribution_source']]:
        pin(data_root/'trading_rules'/entry['file'],entry['sha256'])
    integrated=data_root/'INTEGRATED_GATE_V2_SHA256.json';pin(integrated)
    for path,expected in read_json(integrated).items():pin(data_root/path,expected)
    calendar=read_json(data_root/'calendar_qualification_v2.json')
    if calendar['status']!='MATCH' or calendar['symmetric_difference']:raise DataBlocked('independent calendar mismatch')
    for entry in calendar['sources']:pin(data_root/'trading_rules'/entry['file'],entry['sha256'])
    for s in registry['universe']:
        name=('sz' if s.startswith('15') else 'sh')+s+'_raw.json'
        path=data_root/'panel'/name;pin(path)
        raw_list=read_json(path);raw={r['date']:r for r in raw_list}
        if len(raw)!=len(raw_list):raise DataBlocked('duplicate raw row '+s)
        previous=None;panel[s]={}
        for d in sessions:
            if d>window['end']:break
            candidates=[r for r in rules['regimes'] if r['symbol']==s and r['start']<=d<=r['end']]
            if len(candidates)!=1:raise DataBlocked('missing or overlapping instrument regime '+s+' '+d)
            r=candidates[0]
            if r['buy_lot_shares']!=100 or r['secondary_bought_shares_sellable']!='NEXT_TRADING_DAY' or r['limit_rounding']!='ROUND_HALF_UP_TO_TICK':
                raise DataBlocked('unsupported instrument rule')
            e_today=[e for e in events if e['status']=='implemented' and e['symbol']==s and e['effective_date']==d]
            if len(e_today)>1:raise DataBlocked('same-day events must be consolidated')
            reference=previous
            for e in e_today:
                if e['phase']=='before_open' and reference is not None:reference=transformed_reference(reference,e['cash_per_old_share'],e['ratio'])
            entry=status.get((s,d))
            if not entry:raise DataBlocked('missing status '+s+' '+d)
            cls=entry['session_class']
            if cls in ('OFFICIAL_FULL_DAY_HALT','OFFICIAL_FULL_DAY_HALT_ACTION'):
                if d in raw:raise DataBlocked('halt/raw source conflict')
                proof=entry['evidence'];pin(data_root/proof['path'],proof['sha256'])
                q={'status':'suspended_verified','suspension_evidence':proof,'session_class':cls,'date':d}
                if reference is None:raise DataBlocked('no reference for halted valuation')
                mark=reference
            elif cls in ('OBSERVED_TRADING_DAILY_TIME_UNKNOWN','OFFICIAL_RESUMPTION_1030'):
                if d not in raw:raise DataBlocked('unknown missing raw quote')
                bar=raw[d];validate_raw_bar(bar)
                q={k:bar[k] for k in ('date','open','high','low','close')}
                q.update(status='observed_daily_conditional',conditional_policy='CLARIFICATION_004',
                         first_print_time='10:30:00+08:00' if cls=='OFFICIAL_RESUMPTION_1030' else 'first_trade_time_unknown',
                         session_class=cls,raw_source_sha256=bar['source_sha256'],execution_tradeability_verified=False)
                pin(bar['source_file'],bar['source_sha256'])
                if cls=='OFFICIAL_RESUMPTION_1030':
                    proof=entry['evidence'];pin(data_root/proof['path'],proof['sha256']);q['status_evidence']=proof
                    exception_report.append({'symbol':s,'date':d,'type':'known_1030_first_print','active':d>=window['start']})
                if reference is not None and (s,d) not in unverified_reference:
                    lo,hi=limit_prices(reference,r['daily_price_limit'],r['tick_cny'])
                    q.update(lower_limit=str(lo),upper_limit=str(hi),limit_evidence=r['source'],limit_reference=str(reference),limit_reference_kind='rule_formula_not_exchange_daily_limit_tape')
                else:
                    if d in executions:raise DataBlocked('missing required execution-day limits')
                    q.update(lower_limit=None,upper_limit=None,limit_evidence=None,limit_reference_kind='not_generated_no_scheduled_order')
                    exception_report.append({'symbol':s,'date':d,'type':'unverified_reference_no_scheduled_order'})
                mark=dec(bar['close'])
            else:raise DataBlocked('unqualified status '+cls)
            panel[s][d]=q
            for e in e_today:
                if e['phase']=='after_close':mark=transformed_reference(mark,e['cash_per_old_share'],e['ratio'])
            previous=mark
    report={'normalization_only_no_strategy_returns':True,'evidence_tier':'CONDITIONAL_FIRST_PRINT_DAILY_PROXY',
            'execution_dates':sorted(executions),'reference_exceptions':exception_report,
            'known_unverified_share_reference_dates':[{'symbol':s,'date':d,'scheduled_order':d in executions} for s,d in sorted(unverified_reference)],
            'source_pins':source_pins}
    return panel,sessions,report
