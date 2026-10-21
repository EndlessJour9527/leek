"""Restore only the six unchanged, previously published E4 input archives."""
import argparse,hashlib,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--archive-dir',required=True);a=ap.parse_args();source=Path(a.archive_dir)
checks=json.loads((root/'INPUT_ARCHIVE_HASHES.json').read_text())['archives']
target=root/'frozen_input';target.mkdir(exist_ok=True)
for row in checks:
 p=source/row['file']
 if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('wrong archive '+str(p))
 with zipfile.ZipFile(p) as z:
  if z.testzip():raise ValueError('CRC failure')
  for info in z.infolist():
   dest=(target/info.filename).resolve()
   if not dest.is_relative_to(target.resolve()):raise ValueError('unsafe path')
   if info.is_dir():continue
   data=z.read(info)
   if dest.exists() and dest.read_bytes()!=data:raise ValueError('refuse overwrite '+str(dest))
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
f=target/'E4_H1_REPRODUCIBLE_v1';pins=json.loads((f/'PORTABLE_SHA256SUMS.json').read_text())
for p,h in pins.items():
 if hashlib.sha256((f/p).read_bytes()).hexdigest()!=h:raise ValueError('bad file '+p)
print('PASS: restored and verified',len(pins),'frozen files')
