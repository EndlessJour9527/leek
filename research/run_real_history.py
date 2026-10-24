"""Research orchestration with an explicit optional single-vendor evidence grade.

Strict history_data.acquire and real_backtest.run remain unchanged. This runner
may continue ONLY on network unavailability of the second price source, never
on malformed or conflicting prices. --allow-single-source must be explicit.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Context, ROUND_HALF_UP, localcontext
import json
from pathlib import Path
import time

from leek.contract import DataBlocked, validate_calendar
from leek.history_data import (fetch, parse_tencent, parse_eastmoney, crosscheck,
    parse_dividends, validate_bars, DIVIDEND_URL, VERSION)
from leek.real_backtest import simulate, checked_config
from leek.replay import canonical, digest, load, atomic_create, source_hash


def acquire(config, config_hash, directory, allow_single_source):
    root=Path(directory); root.mkdir(parents=True,exist_ok=False)
    cache=root/'raw'; cache.mkdir(); sources=[]
    def get(url,name):
        raw,meta=fetch(url,cache,name); sources.append(meta); return raw
    first,last=config['warmup_start'],config['evaluation_end']
    bars=[]; calendar=[]
    for year in range(int(first[:4]),int(last[:4])+1):
        url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,{year}-01-01,{year}-12-31,640,'
        rows=parse_tencent(get(url,f'tencent-510300-{year}.json'))
        bars.extend(b for b in rows if first<=b['date']<=last and b['date'][:4]==str(year))
        time.sleep(0.4)
        url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,{year}-01-01,{year}-12-31,640,'
        index=json.loads(get(url,f'tencent-index-{year}.json')).get('data',{}).get('sh000001',{})
        if not index.get('day'): raise DataBlocked('raw index calendar missing')
        calendar.extend(r[0] for r in index['day'] if first<=r[0]<=last and r[0][:4]==str(year))
        time.sleep(0.4)
    validate_bars(bars); validate_calendar(calendar)
    if calendar!=[b['date'] for b in bars]: raise DataBlocked('ETF/index session mismatch')
    counts=dict(sorted(Counter(calendar_day[:4] for calendar_day in calendar).items()))
    if len(counts)!=int(last[:4])-int(first[:4])+1 or any(not 220<=n<=260 for n in counts.values()):
        raise DataBlocked('missing/truncated year of history')
    url=('https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=101&fqt=0'+
        '&beg='+first.replace('-','')+'&end='+last.replace('-','')+
        '&lmt=10000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
    try:
        em_raw=get(url,'eastmoney-510300.json')
    except (OSError,TimeoutError) as exc:
        if not allow_single_source: raise
        quality={'status':'SECOND_PRICE_SOURCE_UNAVAILABLE','differing_cells':None,
                 'primary_vendor':'Tencent','reason':type(exc).__name__+': '+str(exc)}
    else:
        em=parse_eastmoney(em_raw)
        em=[b for b in em if first<=b['date']<=last]
        quality=dict(status='MATCH',primary_vendor='Eastmoney',**crosscheck(em,bars))
        bars=em
    events=parse_dividends(get(DIVIDEND_URL,'dividends.html'),first,last)
    # A frozen change detector; it is not a claim of complete certified CA history.
    expected={'2019-01-16':'0.059','2019-12-11':'0.062','2021-01-18':'0.072',
              '2022-01-19':'0.075','2023-01-16':'0.064','2024-01-18':'0.069','2025-06-18':'0.088'}
    from leek.ledger import dec
    if {e['ex_date']:dec(e['cash_per_share']) for e in events}!={d:dec(v) for d,v in expected.items() if first<=d<=last}:
        raise DataBlocked('distribution history changed; review required')
    data=dict(version=VERSION,instrument='510300',synthetic=False,adjustment='raw',calendar=calendar,
        bars=bars,dividends=events,metadata=dict(config_sha256=config_hash,
            retrieved_at=datetime.now(timezone.utc).isoformat(),sources=sources,crosscheck=quality,
            annual_sessions=counts,calendar_check='Tencent SSE Composite session proxy',
            company_actions_complete_certified=False,historical_point_in_time_certified=False))
    atomic_create(root/'dataset.json',data)
    return data


def evidence_allowed(metadata,allow_single_source):
    quality=metadata.get('crosscheck',{})
    if quality.get('status')=='MATCH' and quality.get('differing_cells')==0:
        return 'CROSS_VENDOR_OHLC_MATCH'
    if (allow_single_source and quality.get('status')=='SECOND_PRICE_SOURCE_UNAVAILABLE'
            and quality.get('differing_cells') is None and quality.get('reason')):
        return 'SINGLE_PRICE_VENDOR_RESEARCH_ONLY'
    raise DataBlocked('crosscheck conflict or single-source research not explicitly allowed')


def execute(data_dir,config_path,output,allow_single_source=False):
    c,config_hash=load(config_path); checked_config(c)
    data,data_hash=load(Path(data_dir)/'dataset.json')
    if (data.get('version')!=VERSION or data.get('synthetic') is not False
            or data.get('adjustment')!='raw' or data.get('instrument')!='510300'):
        raise DataBlocked('real raw 510300 dataset required')
    if data['metadata'].get('config_sha256')!=config_hash: raise DataBlocked('config binding changed')
    if data['calendar']!=[b['date'] for b in data['bars']]: raise DataBlocked('calendar not aligned')
    grade=evidence_allowed(data['metadata'],allow_single_source)
    binding=dict(input_sha256=data_hash,config_sha256=config_hash,source_sha256=source_hash(),
                 driver_sha256=digest(Path(__file__).read_bytes()))
    output=Path(output)
    if output.exists(): raise DataBlocked('refuse existing output')
    results={}
    with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
        for name,cost in c['cost_cases'].items():
            for strategy in c['strategies']:
                results[name+'__'+strategy]=simulate(data['bars'],data['dividends'],c,strategy,cost)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status='COMPLETED_REAL_HISTORY_CONDITIONAL',evidence_grade=grade,binding=binding,
        audit=data['metadata'],protocol=c,results={k:v['summary'] for k,v in results.items()},
        automatic_promotion=False,untouched_holdout=False)
    for key,value in results.items(): atomic_create(output/(key+'.json'),dict(binding=binding,evidence_grade=grade,**value))
    atomic_create(output/'summary.json',report)
    print(json.dumps({'DATA_AUDIT':{'bars':len(data['bars']),'first':data['calendar'][0],
        'last':data['calendar'][-1],'dividends':len(data['dividends']),
        'annual_sessions':data['metadata']['annual_sessions'],'evidence_grade':grade,
        'crosscheck':data['metadata']['crosscheck'],'binding':binding}},sort_keys=True))
    for key,value in results.items(): print(json.dumps({'RESULT':key,**value['summary']},sort_keys=True))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True); p.add_argument('--output',required=True)
    p.add_argument('--config',default='research/real_history_protocol.json')
    p.add_argument('--fetch',action='store_true'); p.add_argument('--allow-single-source',action='store_true')
    a=p.parse_args()
    if a.fetch:
        config,h=load(a.config); checked_config(config); acquire(config,h,a.data_dir,a.allow_single_source)
    execute(a.data_dir,a.config,a.output,a.allow_single_source)

if __name__=='__main__': main()
