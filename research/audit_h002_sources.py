"""Read already downloaded snapshots; export only discrepancies and evidence.

Never repairs a feed, approves a dataset, or runs a strategy. Suitable after a
failed acquisition. This small report is derived; full provider files stay local.
"""
import argparse
from pathlib import Path
from decimal import Decimal
import json

from leek.history_data import parse_eastmoney, parse_tencent
from leek.replay import atomic_create, digest


def inspect(data_dir):
    raw=Path(data_dir)/'raw'
    report={'status':'INCOMPLETE_SOURCE_AUDIT','automatic_promotion':False,
            'source_hashes':{},'missing':[],'mismatches':[],
            'differences_resolved':False}
    tencent=[]
    for year in range(2019,2026):
        path=raw/f'tencent-510300-{year}.json'
        if not path.exists(): report['missing'].append(path.name); continue
        b=path.read_bytes(); report['source_hashes'][path.name]=digest(b)
        tencent.extend(x for x in parse_tencent(b) if x['date'][:4]==str(year))
    path=raw/'eastmoney-510300.json'
    if not path.exists(): report['missing'].append(path.name); return report
    b=path.read_bytes(); report['source_hashes'][path.name]=digest(b)
    eastmoney=[x for x in parse_eastmoney(b) if '2019-01-01'<=x['date']<='2025-12-31']
    if report['missing']: return report
    a={x['date']:x for x in eastmoney}; b={x['date']:x for x in tencent}
    report['missing_dates_tencent']=sorted(set(a)-set(b))
    report['missing_dates_eastmoney']=sorted(set(b)-set(a))
    report['common_sessions']=len(set(a)&set(b))
    for day in sorted(set(a)&set(b)):
        for field in ('open','close','high','low'):
            v1=a[day][field]; v2=b[day][field]
            if Decimal(v1)!=Decimal(v2):
                report['mismatches'].append({'date':day,'field':field,
                    'eastmoney':v1,'tencent':v2,'delta':str(Decimal(v1)-Decimal(v2))})
    report['differing_cells']=len(report['mismatches'])
    report['differing_days']=len({x['date'] for x in report['mismatches']})
    report['status']='SOURCE_CONFLICT' if (report['mismatches'] or report['missing_dates_tencent'] or report['missing_dates_eastmoney']) else 'MATCH_THIS_SNAPSHOT_ONLY'
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=False)
    try:
        report=inspect(a.data_dir)
    except (ValueError,OSError,KeyError) as e:
        report={'status':'AUDIT_PARSE_ERROR','error':type(e).__name__+': '+str(e),
                'automatic_promotion':False,'differences_resolved':False}
    atomic_create(out/'source-audit.json',report)
    print(json.dumps({'SOURCE_AUDIT':report},sort_keys=True))

if __name__=='__main__': main()
