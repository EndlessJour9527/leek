"""Direct-vendor historical ingestion. No credentials, broker, or synthetic fallback.

Raw responses remain in the caller's local directory, never printed or uploaded
by our CI. Public vendor access is not a redistribution license or a guarantee
that the vendor's historical revisions were available at the original date.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone, date
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

from .contract import DataBlocked, validate_calendar, validate_raw_bar
from .ledger import dec
from .replay import canonical, load

VERSION = 'real-history.dataset.v1'
FIELDS = ('open', 'close', 'high', 'low')
DIVIDEND_URL = 'https://fundf10.eastmoney.com/fhsp_510300.html'


def fetch(url, cache, name):
    """Save exact bytes exclusively; bounded HTTPS GET, one retry."""
    if not url.startswith('https://'):
        raise DataBlocked('HTTPS required')
    destination = Path(cache) / name
    if destination.exists():
        raise DataBlocked('refuse existing snapshot: ' + name)
    for attempt in range(2):
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0',
                              'Referer': 'https://quote.eastmoney.com/'})
            with urlopen(request, timeout=25) as response:
                raw = response.read(5000001)
            if len(raw) > 5000000:
                raise DataBlocked('oversized vendor response')
            break
        except (OSError, TimeoutError):
            if attempt:
                raise
            time.sleep(1)
    with destination.open('xb') as handle:
        handle.write(raw)
    return raw, {'url': url, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw),
                 'snapshot_name': name}


def validate_bars(bars):
    if not isinstance(bars, list) or not bars:
        raise DataBlocked('empty historical bars')
    days = []
    for bar in bars:
        if set(bar) != {'date', 'open', 'close', 'high', 'low', 'volume_lots'}:
            raise DataBlocked('historical bar fields mismatch')
        validate_raw_bar(bar)
        for field in FIELDS:
            if not isinstance(bar[field], str) or len(bar[field]) > 32:
                raise DataBlocked('decimal text prices required')
            if not 0 < dec(bar[field]) < 10000:
                raise DataBlocked('ETF price outside supported range')
            if dec(bar[field]) % Decimal('0.001'):
                raise DataBlocked('ETF price exceeds tick precision')
        if not isinstance(bar['volume_lots'], str) or dec(bar['volume_lots']) <= 0:
            raise DataBlocked('zero/missing volume; explicit suspension handling required')
        days.append(bar['date'])
    validate_calendar(days)


def parse_eastmoney(raw, code='510300'):
    data = json.loads(raw).get('data')
    if not data or data.get('code') != code or not data.get('klines'):
        raise DataBlocked('vendor returned wrong or missing instrument')
    bars = []
    for line in data['klines']:
        fields = line.split(',')
        if len(fields) != 11:
            raise DataBlocked('Eastmoney schema drift')
        bars.append(dict(date=fields[0], open=fields[1], close=fields[2],
                         high=fields[3], low=fields[4], volume_lots=fields[5]))
    validate_bars(bars)
    return bars


def parse_tencent(raw, code='sh510300'):
    data = json.loads(raw).get('data', {}).get(code, {})
    # Never substitute adjusted data if the unadjusted day field disappears.
    if 'day' not in data or not isinstance(data['day'], list):
        raise DataBlocked('Tencent unadjusted daily series missing')
    bars = []
    for fields in data['day']:
        if len(fields) < 6:
            raise DataBlocked('Tencent schema drift')
        bars.append(dict(date=fields[0], open=str(fields[1]), close=str(fields[2]),
                         high=str(fields[3]), low=str(fields[4]), volume_lots=str(fields[5])))
    validate_bars(bars)
    return bars


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.capture=False; self.cell=''
    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row=[]
        if tag in ('td', 'th'): self.capture=True; self.cell=''
    def handle_data(self, value):
        if self.capture: self.cell += value.strip()
    def handle_endtag(self, tag):
        if tag in ('td', 'th'): self.row.append(self.cell); self.capture=False
        if tag == 'tr' and self.row: self.rows.append(self.row)


def parse_dividends(raw, first, last):
    table=Tables(); table.feed(raw.decode('utf-8'))
    events=[]
    for row in table.rows:
        if len(row) == 5 and re.fullmatch(r'\d{4}-\d{2}-\d{2}', row[2]):
            if not first <= row[2] <= last:
                continue
            match=re.fullmatch(r'每10份派现金([0-9.]+)元', row[3])
            if not match:
                raise DataBlocked('unsupported dividend format')
            record, ex, pay = row[1], row[2], row[4]
            for day in (record, ex, pay):
                if date.fromisoformat(day).isoformat() != day:
                    raise DataBlocked('invalid distribution date')
            if not record < ex <= pay:
                raise DataBlocked('distribution dates out of order')
            events.append(dict(event_id='D'+ex.replace('-',''), record_date=record,
                ex_date=ex, pay_date=pay, cash_per_share=str(dec(match[1])/10),
                source_url=DIVIDEND_URL))
        if any('拆分' in x or '折算' in x for x in row):
            dates=[x for x in row if re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)]
            if any(first <= x <= last for x in dates):
                raise DataBlocked('unsupported split in research period')
    if not events or len({e['ex_date'] for e in events}) != len(events):
        raise DataBlocked('missing or duplicate distribution history')
    return sorted(events, key=lambda x: x['ex_date'])


def crosscheck(primary, secondary):
    """Require exact dates and OHLC: don't hide one-tick disagreements."""
    if [x['date'] for x in primary] != [x['date'] for x in secondary]:
        raise DataBlocked('cross-provider session mismatch')
    differences=[]
    for a,b in zip(primary,secondary):
        for field in FIELDS:
            if dec(a[field]) != dec(b[field]):
                differences.append((a['date'], field, str(dec(a[field])-dec(b[field]))))
    if differences:
        raise DataBlocked('cross-provider OHLC disagreement: '+str(differences[:12])+
                          '; cells='+str(len(differences)))
    return dict(sessions=len(primary), ohlc_cells=4*len(primary), differing_cells=0,
                volume_compared=False)


def acquire(config_path, output):
    config, config_hash=load(config_path)
    if config['instrument'] != '510300':
        raise DataBlocked('this adapter version is scoped to 510300')
    first,last=config['warmup_start'],config['evaluation_end']
    directory=Path(output); directory.mkdir(parents=True,exist_ok=False)
    snapshots=directory/'raw'; snapshots.mkdir()
    provenance=[]
    def get(url,name):
        raw,meta=fetch(url,snapshots,name); provenance.append(meta); return raw
    base='https://push2his.eastmoney.com/api/qt/stock/kline/get?'
    suffix=('&klt=101&fqt=0&beg='+first.replace('-','')+'&end='+last.replace('-','')+
            '&lmt=10000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
    primary=parse_eastmoney(get(base+'secid=1.510300'+suffix,'eastmoney-510300.json'))
    primary=[b for b in primary if first <= b['date'] <= last]
    secondary=[]
    for year in range(int(first[:4]),int(last[:4])+1):
        url=('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param='+
             f'sh510300,day,{year}-01-01,{year}-12-31,640,')
        rows=parse_tencent(get(url,f'tencent-{year}.json'))
        secondary.extend(b for b in rows if first <= b['date'] <= last and b['date'][:4]==str(year))
        time.sleep(0.2)
    validate_bars(primary); validate_bars(secondary)
    from .history_adjudication import reconcile_sources
    primary,comparison=reconcile_sources(primary,secondary,snapshots,'eastmoney-510300.json',
        [f'tencent-{year}.json' for year in range(int(first[:4]),int(last[:4])+1)])
    index=json.loads(get(base+'secid=1.000001'+suffix,'eastmoney-calendar.json')).get('data') or {}
    if index.get('code') != '000001': raise DataBlocked('wrong calendar proxy instrument')
    calendar=[x.split(',')[0] for x in index.get('klines',[]) if first<=x.split(',')[0]<=last]
    validate_calendar(calendar)
    if calendar != [b['date'] for b in primary]:
        raise DataBlocked('ETF/index calendar coverage mismatch')
    counts=dict(sorted(Counter(d[:4] for d in calendar).items()))
    if any(not 220<=n<=260 for n in counts.values()) or len(counts)!=int(last[:4])-int(first[:4])+1:
        raise DataBlocked('unexpected annual coverage / silently truncated response')
    events=parse_dividends(get(DIVIDEND_URL,'eastmoney-dividends.html'),first,last)
    # Known schedule is a change detector, NOT proof of complete corporate actions.
    expected={'2019-01-16':'0.059','2019-12-11':'0.062','2021-01-18':'0.072',
              '2022-01-19':'0.075','2023-01-16':'0.064','2024-01-18':'0.069','2025-06-18':'0.088'}
    if {e['ex_date']:dec(e['cash_per_share']) for e in events} != {d:dec(v) for d,v in expected.items() if first<=d<=last}:
        raise DataBlocked('distribution schedule changed; review required')
    payload=dict(version=VERSION,instrument='510300',synthetic=False,adjustment='raw',
        calendar=calendar,bars=primary,dividends=events,
        metadata=dict(retrieved_at=datetime.now(timezone.utc).isoformat(),sources=provenance,
            config_sha256=config_hash,crosscheck=comparison,annual_sessions=counts,
            calendar_check='same ETF on two vendors plus SSE Composite sessions; not exchange-certified',
            company_actions_complete_certified=False,historical_point_in_time_certified=False))
    (directory/'dataset.json').write_bytes(canonical(payload))
    print(json.dumps({'DATA_AUDIT':{'first':calendar[0],'last':calendar[-1],'annual_sessions':counts,
          'bars':len(primary),'dividends':len(events),'crosscheck':comparison,
          'normalized_sha256':sha256(canonical(payload)).hexdigest()}},sort_keys=True))
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default='research/real_history_protocol.json')
    p.add_argument('--output',required=True)
    a=p.parse_args(); acquire(a.config,a.output)

if __name__=='__main__': main()
