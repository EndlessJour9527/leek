"""Single immutable independent-audit release; no boolean-only historical bypass."""
import hashlib,json
from pathlib import Path
from contract import DataBlocked,verify_pins
from registration_guard import read_registration,FINAL_AMENDMENT_HASH
from adapter import read_json,sha

def content_hash(value):
    from batch_artifacts import encode
    return hashlib.sha256((json.dumps(value,default=encode,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()).hexdigest()

class VerifiedRelease:
    def __init__(self,path,expected_sha256):
        path=Path(path).resolve()
        if sha(path)!=expected_sha256:raise DataBlocked('release hash differs from independent approval')
        self.data=read_json(path);self.path=path;self.sha256=expected_sha256
        d=self.data
        if d['status']!='APPROVED_FOR_CONDITIONAL_H1_BATCH' or d['account_path_budget']!=15 or d['evidence_tier']!='CONDITIONAL_FIRST_PRINT_DAILY_PROXY':
            raise DataBlocked('release scope differs')
        if d['registration_final_manifest_sha256']!=FINAL_AMENDMENT_HASH:raise DataBlocked('release registration differs')
        engine=Path(__file__).resolve().parent
        actual={p.name:sha(p) for p in sorted(engine.glob('*.py'))}
        if actual!=d['engine_hashes']:raise DataBlocked('engine code differs from reviewed code')
        manifest=Path(d['candidate_manifest_path']).resolve()
        if sha(manifest)!=d['candidate_manifest_sha256']:raise DataBlocked('normalized manifest differs')
        self.candidate=manifest.parent;self.candidate_hashes=read_json(manifest)
        verify_pins(self.candidate,[dict(path=p,sha256=h) for p,h in self.candidate_hashes.items()])
        if not d['evidence_pins']:raise DataBlocked('no independent evidence binding')
        for p,h in d['evidence_pins'].items():
            if sha(p)!=h:raise DataBlocked('evidence changed '+p)
        report=read_json(self.candidate/'adapter_report.json')
        for p,h in report['source_pins'].items():
            if sha(p)!=h:raise DataBlocked('adapter source changed '+p)
        self.registry,_=read_registration(self.candidate.parent/'registration')
        window=read_json(self.candidate/'window.json')
        if window['start']!='2021-10-18' or window['end']!='2026-06-30':raise DataBlocked('release is only the frozen H1 prefix')
        odd=d['odd_lot_exit_allowed']
        if set(odd)!=set(self.registry['universe']) or not all(isinstance(v,bool) for v in odd.values()):raise DataBlocked('odd-lot rule not explicit')
        self.qualification={'fixture_kind':'INDEPENDENTLY_RELEASED_H1_HISTORY','release_path':str(path),'release_sha256':expected_sha256,
                            'odd_lot_exit_allowed':odd,'evidence_tier':d['evidence_tier'],'limitations':d['limitations'],
                            'execution_tradeability_verified':False,'historical_intraday_status_complete':False,'capacity_verified':False,
                            'cash_settlement_cent_rounding_verified':False}

        self._qualification_digest=content_hash(self.qualification)

    def validate_inputs(self,panel,sessions,events,window,registry):
        if content_hash(self.qualification)!=self._qualification_digest:raise DataBlocked('release qualification mutated')
        if registry!=self.registry:raise DataBlocked('registry changed after release')
        for name,value in [('panel',panel),('sessions',sessions),('events',events),('window',window)]:
            if content_hash(value)!=self.candidate_hashes[name+'.json']:raise DataBlocked('in-memory input changed: '+name)


def execute_released(release_path,expected_sha256,output):
    from batch_artifacts import execute_batch
    release=VerifiedRelease(release_path,expected_sha256)
    c=release.candidate
    return execute_batch(read_json(c/'panel.json'),read_json(c/'sessions.json'),read_json(c/'events.json'),release.registry,
                         read_json(c/'window.json'),release.qualification,output,c.parent/'registration',release=release)
