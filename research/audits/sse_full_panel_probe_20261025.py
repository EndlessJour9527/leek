"""One-shot SSE/Tencent 2019–2025 OHLC feasibility probe, NOT strategy approval.

Distinct from the frozen Eastmoney/Tencent history contract. No market panel,
private evidence or credentials published; output only provenance hashes,
coverage counts and bounded mismatches. Official SSE mapping was separately
reviewed in DQ001's 2026-10-25 evidence; whole-panel basis is NOT certified.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

SSE = 'https://yunhq.sse.com.cn:32042/v1/sh1/dayk/510300?begin=-2000&end=-1&period=day'
TX = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,{y}-01-01,{y}-12-31,640,'
EXPECTED = {'2019':244, '2020':243, '2021':243, '2022':242, '2023':242, '2024':242, '2025':243}
SELECTED_SHA = 'b0abbe0e470c1db379958de754dfa3ec75414c98ca45254143e4ba043289dfc9'
FIELDS = ('open', 'high', 'low', 'close')

class Blocked(ValueError):
    pass

def dec(value):
    try: v=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError) as exc: raise Blocked('invalid quote') from exc
    if not v.is_finite() or not 0<v<1000: raise Blocked('invalid quote scale')
    return v

def normalize(rows):
    out={}
    for day, price in rows:
        if not isinstance(day,str) or not re.fullmatch(r'20\d\d-\d\d-\d\d',day):
            raise Blocked('invalid calendar date')
        if datetime.strptime(day,'%Y-%m-%d').strftime('%Y-%m-%d')!=day: raise Blocked('invalid date')
        if day in out: raise Blocked('duplicate day')
        if set(price)!=set(FIELDS): raise Blocked('incomplete OHLC')
        p={k:dec(price[k]) for k in FIELDS}
        if p['high']<max(p['open'],p['close'],p['low']) or p['low']>min(p['open'],p['close'],p['high']):
            raise Blocked('inconsistent OHLC range')
        out[day]=p
    if not out or list(out)!=sorted(out): raise Blocked('unordered or empty daily series')
    return out

def sse_parse(raw):
    try: doc=json.loads(raw)
    except (ValueError,UnicodeError) as exc: raise Blocked('SSE JSON invalid') from exc
    if not isinstance(doc,dict) or str(doc.get('code'))!='510300': raise Blocked('SSE identity changed')
    items=doc.get('kline')
    if not isinstance(items,list): raise Blocked('SSE kline missing')
    rows=[]
    for row in items:
        if not isinstance(row,list) or len(row)<6 or not re.fullmatch(r'20\d{6}',str(row[0])):
            raise Blocked('SSE row schema changed')
        d=str(row[0]); day=d[:4]+'-'+d[4:6]+'-'+d[6:8]
        if '2019-01-01'<=day<='2025-12-31':
            # SSE official chart mapping: date,open,high,low,close,volume.
            rows.append((day,dict(open=row[1],high=row[2],low=row[3],close=row[4])))
    return normalize(rows)

def tx_parse(raw):
    try: rows=json.loads(raw)['data']['sh510300']['day']
    except (KeyError,ValueError,TypeError,UnicodeError) as exc: raise Blocked('Tencent raw day unavailable') from exc
    if not isinstance(rows,list): raise Blocked('Tencent rows invalid')
    out=[]
    for row in rows:
        if not isinstance(row,list) or len(row)<6: raise Blocked('Tencent schema changed')
        day=row[0]
        if isinstance(day,str) and '2019-01-01'<=day<='2025-12-31':
            out.append((day,dict(open=row[1],close=row[2],high=row[3],low=row[4])))
    return normalize(out)

def compare(sse,tx,expected_cells):
    years_a=dict(sorted(Counter(x[:4] for x in sse).items()))
    years_b=dict(sorted(Counter(x[:4] for x in tx).items()))
    if years_a!=EXPECTED or years_b!=EXPECTED: raise Blocked('year coverage mismatch')
    if list(sse)!=list(tx): raise Blocked('different trading calendars')
    diff=[(day,f,sse[day][f],tx[day][f]) for day in sse for f in FIELDS
          if sse[day][f]!=tx[day][f]]
    changed=[(d,f) for (d,f),v in expected_cells.items()
             if d not in sse or sse[d][f]!=v or tx[d][f]!=v]
    return dict(sessions=len(sse),ohlc_cells=4*len(sse),annual_sessions=years_a,
                differing_cells=len(diff),reviewed_cell_disagreements=len(changed),
                differing_years=dict(sorted(Counter(d[:4] for d,_,_,_ in diff).items())),
                limited_mismatches=[dict(date=d,field=f,sse=str(a),tencent=str(b))
                                    for d,f,a,b in diff[:25]])

def get(url):
    req=Request(url,headers={'Accept':'application/json','User-Agent':'Leek-BoundedSourceProbe/1.0'})
    with urlopen(req,timeout=18) as response:
        if response.status!=200: raise Blocked('supplier HTTP not 200')
        raw=response.read(5_000_001)
    if not raw or len(raw)>5_000_000: raise Blocked('supplier response size invalid')
    return raw

def probe(repo_root):
    path=repo_root/'research/results/DQ001_exchange_evidence.json'
    body=path.read_bytes()
    if sha256(body).hexdigest()!=SELECTED_SHA: raise Blocked('reviewed evidence hash mismatch')
    evidence=json.loads(body)
    cells=evidence['cells']
    if len(cells)!=20: raise Blocked('reviewed DQ001 cell count changed')
    selected={(c['date'],c['field']):dec(c['tencent']) for c in cells}
    if len(selected)!=20: raise Blocked('duplicate reviewed DQ001 cell')
    sources=[]
    raw=get(SSE)
    sources.append(dict(source='SSE',url=SSE,sha256=sha256(raw).hexdigest(),bytes=len(raw)))
    sse=sse_parse(raw)
    tx={}
    for y in EXPECTED:
        url=TX.format(y=y)
        raw=get(url)
        sources.append(dict(source='Tencent',year=y,url=url,
                            sha256=sha256(raw).hexdigest(),bytes=len(raw)))
        yearbars=tx_parse(raw)
        if any(d[:4]!=y for d in yearbars) or set(tx)&set(yearbars):
            raise Blocked('Tencent year overlap/schema')
        tx.update(yearbars)
    result=compare(sse,tx,selected)
    status=('SOURCE_CONSISTENCY_CANDIDATE' if result['differing_cells']==0
            and result['reviewed_cell_disagreements']==0 else 'BLOCKED_SOURCE_DIFFERENCES')
    return status,result,sources

def main():
    report=dict(schema='sse-tencent-full-panel-probe.v1',
                created_at_utc=datetime.now(timezone.utc).isoformat(),
                period=['2019-01-01','2025-12-31'],historical_strategy_runs=0,
                strategy_conclusions=0,full_input_approved=False,
                new_data_source_version_review_required=True,
                raw_market_data_published=False,already_consumed_development_sample=True)
    try:
        status,quality,sources=probe(Path(__file__).resolve().parents[2])
        report.update(status=status,quality=quality,sources=sources)
    except (Blocked,ValueError,OSError,KeyError,TypeError) as exc:
        report.update(status='BLOCKED_SOURCE_PROBE',reason=type(exc).__name__+': '+str(exc)[:150])
    artifact=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'sse-tencent-full-panel-probe-20261025.json'
    artifact.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
    print(json.dumps({k:report.get(k) for k in ('status','quality','reason','full_input_approved')},sort_keys=True))
    return 0 if report['status']=='SOURCE_CONSISTENCY_CANDIDATE' else 2

if __name__=='__main__': raise SystemExit(main())
