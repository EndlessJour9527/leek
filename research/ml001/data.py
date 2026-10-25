"""Explicit ML001 SSE/Tencent panel v1; private raw data, never legacy relabelling."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from leek.contract import DataBlocked, validate_calendar
from leek.history_data import (parse_tencent, parse_dividends, validate_bars,
                               crosscheck, DIVIDEND_URL)
from leek.real_backtest import checked_events

VERSION = 'ML001_SSE_TENCENT_PANEL_V1'
FIRST, LAST = '2019-01-01', '2025-12-31'
SSE_URL = 'https://yunhq.sse.com.cn:32042/v1/sh1/dayk/510300?begin=-2500&end=-1&period=day'
EXPECTED_EVENTS = {'2019-01-16':'0.059','2019-12-11':'0.062','2021-01-18':'0.072',
 '2022-01-19':'0.075','2023-01-16':'0.064','2024-01-18':'0.069','2025-06-18':'0.088'}


def encoded(obj):
    return (json.dumps(obj,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def routes():
    result = {'sse.json': SSE_URL, 'dividends.html': DIVIDEND_URL}
    for year in range(2019,2026):
        for name,symbol in [('etf','sh510300'),('calendar','sh000001')]:
            result[f'{name}-{year}.json'] = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param='
                f'{symbol},day,{year}-01-01,{year}-12-31,640,')
    return result


def parse_sse(raw):
    payload=json.loads(raw,parse_float=Decimal)
    if str(payload.get('code'))!='510300' or not isinstance(payload.get('kline'),list):
        raise DataBlocked('SSE wrong symbol or missing kline')
    rows=[]
    for values in payload['kline']:
        if not isinstance(values,list) or len(values) not in (6,7):
            raise DataBlocked('SSE daily schema changed')
        day=str(values[0])
        if len(day)!=8 or not day.isdigit():raise DataBlocked('SSE date format')
        day=f'{day[:4]}-{day[4:6]}-{day[6:]}'
        if FIRST<=day<=LAST:
            # Volume unit differs from Tencent. Never compare or combine units.
            rows.append(dict(date=day,open=str(values[1]),high=str(values[2]),
                             low=str(values[3]),close=str(values[4]),volume_lots=str(values[5])))
    validate_bars(rows)
    return rows


def reconstruct(raws):
    if set(raws)!=set(routes()):raise DataBlocked('source set incomplete or changed')
    primary=parse_sse(raws['sse.json']);secondary=[];calendar=[]
    for year in range(2019,2026):
        secondary.extend(b for b in parse_tencent(raws[f'etf-{year}.json'])
                         if b['date'][:4]==str(year) and FIRST<=b['date']<=LAST)
        obj=json.loads(raws[f'calendar-{year}.json']).get('data',{}).get('sh000001',{})
        if not isinstance(obj.get('day'),list) or not obj['day']:
            raise DataBlocked('raw index calendar missing')
        calendar.extend(row[0] for row in obj['day']
                        if row[0][:4]==str(year) and FIRST<=row[0]<=LAST)
    validate_calendar(calendar);validate_bars(secondary)
    if calendar!=[b['date'] for b in secondary]:raise DataBlocked('calendar missing or extra session')
    counts=dict(sorted(Counter(d[:4] for d in calendar).items()))
    if set(counts)!={str(y) for y in range(2019,2026)} or any(not 220<=n<=260 for n in counts.values()):
        raise DataBlocked('truncated annual panel')
    audit=crosscheck(primary,secondary) # strict Decimal equality, no correction
    # Preserve prior reviewed DQ001 prices, not majority selection or relabelled approval.
    ref=Path(__file__).resolve().parents[1]/'results/DQ001_source_audit.json'
    conflicts=json.loads(ref.read_text())['mismatches'];byday={b['date']:b for b in primary}
    if len(conflicts)!=20:raise DataBlocked('unexpected frozen DQ001 scope')
    for cell in conflicts:
        if Decimal(byday[cell['date']][cell['field']])!=Decimal(cell['tencent']):
            raise DataBlocked('SSE panel changed previously reviewed DQ001 cell')
    # Trading OHLC from SSE; volume feature deliberately from its separate Tencent source.
    bars=[{**a,'volume_lots':b['volume_lots']} for a,b in zip(primary,secondary)]
    events=parse_dividends(raws['dividends.html'],FIRST,LAST)
    if {e['ex_date']:Decimal(e['cash_per_share']) for e in events}!={k:Decimal(v) for k,v in EXPECTED_EVENTS.items()}:
        raise DataBlocked('distribution change detector failed')
    checked_events(events,bars)
    lookup={d:i for i,d in enumerate(calendar)}
    if any(lookup[e['ex_date']]!=lookup[e['record_date']]+1 for e in events):
        raise DataBlocked('label dividend convention needs adjacent record/ex dates')
    return dict(version=VERSION,synthetic=False,instrument='510300',bars=bars,dividends=events,
                calendar=calendar,audit={**audit,'annual_sessions':counts,
                'grade':'SSE_TENCENT_EXACT_OHLC_CONDITIONAL_RESEARCH',
                'raw_price_semantics':'SSE nominal daily fields corroborated by Tencent day',
                'point_in_time_certified':False,'company_actions_complete_certified':False,
                'live_fill_certified':False,'automatic_promotion':False})


def fetch_panel(directory):
    root=Path(directory)
    if root.exists():raise DataBlocked('refuse existing input directory')
    root.mkdir(parents=True);(root/'raw').mkdir()
    provenance=[];raws={}
    for name,url in routes().items():
        req=Request(url,headers={'User-Agent':'LeekResearch/ML001',
                                 'Referer':'https://www.sse.com.cn/' if name=='sse.json' else 'https://quote.eastmoney.com/'})
        # One bounded request per route. No retries, cookies, credentials or refusal bypass.
        with urlopen(req,timeout=30) as response:
            raw=response.read(5_000_001)
        if len(raw)>5_000_000:raise DataBlocked('oversized source')
        (root/'raw'/name).write_bytes(raw);raws[name]=raw
        provenance.append(dict(name=name,url=url,sha256=sha256(raw).hexdigest(),bytes=len(raw)))
        time.sleep(.15)
    panel=reconstruct(raws)
    panel['provenance']=provenance
    panel['retrieved_at_utc']=datetime.now(timezone.utc).isoformat()
    (root/'dataset.json').write_bytes(encoded(panel))
    return load_panel(root)


def load_panel(directory):
    root=Path(directory).resolve();path=root/'dataset.json'
    if path.is_symlink():raise DataBlocked('symlink dataset')
    panel=json.loads(path.read_text())
    if panel.get('version')!=VERSION or panel.get('synthetic') is not False:
        raise DataBlocked('not a real ML001 panel')
    source=panel.get('provenance',[])
    if len(source)!=len(routes()) or {r.get('name') for r in source}!=set(routes()):
        raise DataBlocked('source provenance set mismatch')
    raws={}
    for entry in source:
        name=entry['name'];p=root/'raw'/name
        if entry['url']!=routes()[name] or p.is_symlink() or p.resolve().parent!=(root/'raw').resolve():
            raise DataBlocked('unexpected provenance route or private source path')
        raw=p.read_bytes()
        if len(raw)!=entry['bytes'] or sha256(raw).hexdigest()!=entry['sha256']:
            raise DataBlocked('raw snapshot checksum mismatch')
        raws[name]=raw
    rebuilt=reconstruct(raws)
    for field in rebuilt:
        if rebuilt[field]!=panel.get(field):raise DataBlocked('normalized panel does not match original sources: '+field)
    return panel
