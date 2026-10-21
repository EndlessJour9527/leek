"""Deterministic new-directory output. Caller must obtain explicit gate approval."""
import hashlib,json
from pathlib import Path
from decimal import Decimal
from run_portfolio import run_path
from registration_guard import read_registration
from contract import DataBlocked

def encode(value):
    if isinstance(value,Decimal):return str(value)
    raise TypeError(type(value).__name__)

def dump(path,value):
    Path(path).write_text(json.dumps(value,default=encode,ensure_ascii=False,sort_keys=True,indent=2)+'\n')

def execute_batch(panel,sessions,events,registry,cost_window,qualification,output,registration_root,release=None):
    frozen,bound=read_registration(registration_root)
    if registry!=frozen:raise DataBlocked('supplied registry differs from frozen registry')
    # Gate before creating any output or calculating any path.
    is_synthetic=qualification.get('fixture_kind')=='HAND_AUTHORED_SYNTHETIC'
    if not is_synthetic:
        from release_gate import VerifiedRelease
        if not isinstance(release,VerifiedRelease):raise DataBlocked('independent hash-bound release is required')
        if qualification!=release.qualification:raise DataBlocked('qualification differs from signed release')
        release.validate_inputs(panel,sessions,events,cost_window,registry)
    output=Path(output)
    if output.exists():raise FileExistsError('never overwrite results')
    output.mkdir(parents=True)
    code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    dump(output/'run_manifest_before_execution.json',{'registry':registry,'registration_hashes':bound,'code_hashes':code,'window':cost_window,'qualification':qualification,'historical_returns':not is_synthetic,'evidence_tier':'CONDITIONAL_FIRST_PRINT_DAILY_PROXY','execution_tradeability_verified':False,'capacity_verified':False})
    for strategy in registry['strategies']:
        for cost in registry['cost_scenarios']:
            engine=run_path(panel,sessions,events,registry,strategy,cost,cost_window,qualification,release=release)
            folder=output/(strategy['id']+'_'+cost['id']);folder.mkdir()
            dump(folder/'metadata.json',{'strategy_id':strategy['id'],'cost_id':cost['id'],'window':cost_window,'initial_cash':engine.initial_cash,'evidence_tier':'CONDITIONAL_FIRST_PRINT_DAILY_PROXY','registration_hashes':bound,'synthetic_fixture':is_synthetic,'release_sha256':release.sha256 if release else None,'cash_settlement_cent_rounding_verified':False})
            for name,rows in [('daily',engine.daily),('signals',engine.signals),('executions',engine.executions),('events',engine.event_log)]:dump(folder/(name+'.json'),rows)
            dump(folder/'terminal.json',{'cash':engine.ledger.cash,'positions':engine.ledger.positions,'receivables':[{'symbol':s,'event_id':e,'amount':v} for (s,e),v in sorted(engine.ledger.receivables.items())],'initial_cash':engine.initial_cash,'no_terminal_liquidation':True})
    checksums={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
    dump(output/'SHA256SUMS.json',checksums)
    return checksums
