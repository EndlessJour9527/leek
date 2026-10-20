"""One frozen H002 experiment; not an optimizer or broker integration.

Reuses PR5 acquisition and identical Ledger execution. Recomputes all controls
on the same snapshot; single-source permission must be explicit. Consumed
2020-2025 data remains development data, never relabelled as holdout.
"""
from __future__ import annotations
import argparse
from decimal import Context, ROUND_HALF_UP, localcontext
import json
from pathlib import Path

from leek.channel_signal import MODEL_ID
from leek.contract import DataBlocked
from leek.real_backtest import checked_config, simulate
from leek.replay import atomic_create, digest, load, source_hash
from research.run_real_history import acquire, execute

BASE_CONFIG_SHA256 = 'f05c7f0fb34ee7d1e73fd57f2f85c2a19758979ae26aed35140a300cef7fde86'
PREREGISTRATION_COMMIT = 'ab34ceb9578aa4dcecf99f437d542c5700054aaf'


def screen(results):
    base=results['base__'+MODEL_ID]; stress=results['stress__'+MODEL_ID]
    comparator=results['base__ma120_1d']
    checks={
        'positive_base_net_return': base['total_return_pct']>0,
        'positive_stress_net_return': stress['total_return_pct']>0,
        'base_return_above_ma120': base['total_return_pct']>comparator['total_return_pct'],
        'base_drawdown_no_worse_than_ma120': abs(base['max_close_drawdown_pct'])<=abs(comparator['max_close_drawdown_pct']),
        'stress_profit_factor_above_one': stress['profit_factor'] is not None and stress['profit_factor']>1,
        'at_least_twenty_closed_trades': stress['closed_trades']>=20,
    }
    return dict(checks=checks,
        decision='RESEARCH_SCREEN_PASS' if all(checks.values()) else 'REJECTED_DEVELOPMENT_SCREEN',
        automatic_promotion=False,untouched_holdout=False,
        explanation='A pass permits only further independent research, never deployment. A fail is retained without parameter hunting.')


def run(data_dir, output, fetch=False, allow_single_source=False):
    root=Path(__file__).resolve().parents[1]
    config_path=root/'research/real_history_protocol.json'
    c,config_hash=load(config_path); checked_config(c)
    if config_hash!=BASE_CONFIG_SHA256: raise DataBlocked('frozen control configuration changed')
    output=Path(output)
    if output.exists(): raise DataBlocked('refuse existing experiment output')
    if fetch: acquire(c,config_hash,data_dir,allow_single_source)
    # execute validates real/raw flag, dates, configuration and evidence grade
    # before creating or publishing reports. H002 consumes precisely that data.
    controls=execute(data_dir,config_path,output/'baseline',allow_single_source)
    data,data_hash=load(Path(data_dir)/'dataset.json')
    if data_hash!=controls['binding']['input_sha256']:
        raise DataBlocked('dataset changed between controls and candidate')
    binding=dict(controls['binding'],source_sha256=source_hash(),
        h002_driver_sha256=digest(Path(__file__).read_bytes()),
        preregistration_sha256=digest((root/'research/H002_PROTOCOL.md').read_bytes()),
        preregistration_commit=PREREGISTRATION_COMMIT)
    results=dict(controls['results']); candidate_reports={}
    with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
        for cost_name,cost in c['cost_cases'].items():
            key=cost_name+'__'+MODEL_ID
            r=simulate(data['bars'],data['dividends'],c,MODEL_ID,cost)
            candidate_reports[key]=r; results[key]=r['summary']
    assessment=screen(results)
    report=dict(status='COMPLETED_H002_REAL_HISTORY_CONDITIONAL',
        evidence_grade=controls['evidence_grade'],binding=binding,
        audit=controls['audit'],protocol=c,results=results,assessment=assessment,
        sample_role='already_consumed_development_sample',
        source_reference='vnpy/vnpy_ctastrategy@c212d603e68a5f4dbbc160fe8f7f8b1e06be2494',
        reproduction_scope='20/10 close-TR channel only; not full Turtle strategy')
    for key,value in candidate_reports.items():
        atomic_create(output/(key+'.json'),dict(binding=binding,evidence_grade=controls['evidence_grade'],**value))
    atomic_create(output/'experiment.json',report)
    print(json.dumps({'H002_ASSESSMENT':assessment,'evidence_grade':report['evidence_grade']},sort_keys=True))
    for key,value in results.items(): print(json.dumps({'H002_COMPARISON':key,**value},sort_keys=True))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True); p.add_argument('--output',required=True)
    p.add_argument('--fetch',action='store_true'); p.add_argument('--allow-single-source',action='store_true')
    a=p.parse_args(); run(a.data_dir,a.output,a.fetch,a.allow_single_source)

if __name__=='__main__': main()
