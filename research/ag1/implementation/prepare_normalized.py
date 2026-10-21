"""Build a reviewable adapter candidate only; never run a strategy."""
from pathlib import Path
from adapter import normalized_cash_events,normalized_share_events,normalize_panel,sha,read_json
from registration_guard import read_registration
from batch_artifacts import dump

def prepare(root,output):
    root=Path(root);output=Path(output)
    if output.exists():raise FileExistsError('candidate is immutable; use a new version')
    registry,bound=read_registration(root/'registration')
    freeze=read_json(root/'data_preflight/EVIDENCE_WINDOW_FREEZE.json')
    window=dict(initial_signal=registry['initial_signal_date'],initial_formation=registry['initial_formation_month'],start=freeze['execution_start'],end=freeze['qualified_candidate_end'],label=freeze['label'])
    cash_path=root/'data_preflight/cash_events_merged_exact_v2.json';shares_path=root/'data_preflight/share_action_events_v2.json'
    events=normalized_cash_events([cash_path],window['end'])+normalized_share_events(shares_path,window['end'])
    panel,sessions,report=normalize_panel(root/'data_preflight',registry,events,window)
    for path in (cash_path,shares_path,root/'data_preflight/EVIDENCE_WINDOW_FREEZE.json'):
        report['source_pins'][str(path.resolve())]=sha(path)
    for e in events:
        for proof in e.get('evidence',[]):
            path=Path(proof['path'])
            if not path.is_absolute():path=root/'data_preflight'/path
            if sha(path)!=proof['sha256']:raise ValueError('event evidence changed')
            report['source_pins'][str(path.resolve())]=sha(path)
    output.mkdir(parents=True)
    for name,value in [('panel',panel),('sessions',sessions),('events',events),('window',window),('adapter_report',report),('registration_bound',bound)]:dump(output/(name+'.json'),value)
    dump(output/'SHA256SUMS.json',{p.name:sha(p) for p in sorted(output.glob('*.json'))})
    return output
if __name__=='__main__':
    import sys
    print(prepare(sys.argv[1],sys.argv[2]))
