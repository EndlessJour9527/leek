"""Bind the original registry and all required prerevenue clarifications."""
import hashlib,json
from pathlib import Path
from contract import DataBlocked,verify_pins

ROOT_MANIFEST_HASH='6eed1cfb809b128a673a945d1031dcb679e04f8ccc01b6c69e9f72c8643da5a4'
FINAL_AMENDMENT_HASH='2bce7aaf2e6344a15413a3edfc0d2cc2d3788bd6d73385f33c9965f3ad9fcb43'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_registration(root):
    root=Path(root)
    original=root/'SHA256SUMS.json'
    if sha(original)!=ROOT_MANIFEST_HASH:raise DataBlocked('original registration root changed')
    base=json.loads(original.read_text())
    verify_pins(root,[{'path':p,'sha256':h} for p,h in base['files'].items()])
    prior=None;bound={str(original.name):sha(original)}
    for name in ('AMENDMENT_SHA256SUMS.json','AMENDMENT_002_SHA256SUMS.json','AMENDMENT_003_SHA256SUMS.json','AMENDMENT_004_SHA256SUMS.json','AMENDMENT_005_SHA256SUMS.json'):
        path=root/name;a=json.loads(path.read_text())
        if a['original_manifest_sha256']!=ROOT_MANIFEST_HASH:raise DataBlocked('amendment origin changed')
        prev=a.get('preceding_amendment_manifest_sha256',a.get('previous_manifest_sha256'))
        if prior and prev!=prior:raise DataBlocked('amendment chain broken')
        verify_pins(root,[{'path':p,'sha256':h} for p,h in a['clarifications'].items()])
        prior=sha(path);bound[name]=prior
    if prior!=FINAL_AMENDMENT_HASH:raise DataBlocked('final amendment changed')
    registry=json.loads((root/'registry.json').read_text(),parse_float=str)
    return registry,bound
