"""Verify public hashes and derived accounting; NOT historical market replay."""
from pathlib import Path
from decimal import Decimal as D
import json,hashlib,gzip
root=Path(__file__).resolve().parent
manifest=json.loads((root/'PUBLIC_MANIFEST.json').read_text())
for p,h in manifest.items():
 assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
paths=0;rows=0
for account in ('CA1','SCASH','BH300','CASH'):
 for cost in ('BASE','DOUBLE'):
  x=json.loads(gzip.decompress((root/'implementation/RESULTS'/f'{account}_{cost}.json.gz').read_bytes()));paths+=1
  assert len(x['daily'])==1140
  for r in x['daily']:
   rows+=1;assert D(r['nav'])==D(r['cash'])+D(r['receivable'])+sum(D(p['value']) for p in r['positions'].values())
   assert all('close' not in p for p in r['positions'].values())
  assert not x['round_trips']
d=json.loads((root/'implementation/RESULTS/DECISION.json').read_text());assert d['decision']=='RETAIN_FOR_FURTHER_EVIDENCE'
print(f'PASS: {paths} complete derived paths, {rows} NAV rows, public hashes; NOT full historical replay')
