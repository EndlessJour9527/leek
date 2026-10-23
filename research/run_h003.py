"""H003 frozen mean-reversion developmental experiment; NOT a broker.

The DQ001 gate executes before network/data access. A verified review record is
required: third-distributor majority agreement alone cannot unlock this study.
"""
from __future__ import annotations
import argparse
from decimal import Context, ROUND_HALF_UP, localcontext
import json
from pathlib import Path

from leek.contract import DataBlocked
from leek.mean_reversion_signal import MODEL_ID
from leek.real_backtest import checked_config, simulate
from leek.replay import atomic_create, digest, load, source_hash
from research.run_h002 import require_data_issue_resolution, BASE_CONFIG_SHA256
from research.run_real_history import acquire, execute

PREREGISTRATION_COMMIT = '90937f5727a0a0f4c84291ce76027d752703100a'


def screen(results):
    base = results['base__' + MODEL_ID]
    stress = results['stress__' + MODEL_ID]
    passive = results['base__buy_hold']
    checks = {
        'positive_base_total_account_return': base['total_return_pct'] > 0,
        'base_beats_same_budget_passive': base['total_return_pct'] > passive['total_return_pct'],
        'positive_stress_total_account_return': stress['total_return_pct'] > 0,
        'base_drawdown_no_worse_than_passive':
            abs(base['max_close_drawdown_pct']) <= abs(passive['max_close_drawdown_pct']),
        'stress_at_least_twenty_closed_trades': stress['closed_trades'] >= 20,
        'stress_profit_factor_above_one':
            stress['profit_factor'] is not None and stress['profit_factor'] > 1,
    }
    return dict(
        decision='RESEARCH_SCREEN_PASS' if all(checks.values()) else 'REJECTED_DEVELOPMENT_SCREEN',
        checks=checks, automatic_promotion=False, untouched_holdout=False,
        explanation='A screening pass is not proof of out-of-sample advantage or fillability; frozen failures remain archived.')


def run(data_dir, output, fetch=False, allow_single_source=False):
    root = Path(__file__).resolve().parents[1]
    registry, _ = load(root / 'research/data_conflicts.json')
    require_data_issue_resolution(registry)  # MUST remain first; no touched market data if unresolved.
    output = Path(output)
    if output.exists():
        raise DataBlocked('refuse to overwrite research output')
    config_path = root / 'research/real_history_protocol.json'
    config, config_hash = load(config_path)
    checked_config(config)
    if config_hash != BASE_CONFIG_SHA256:
        raise DataBlocked('original controls or fees changed')
    if fetch:
        acquire(config, config_hash, data_dir, allow_single_source)
    controls = execute(data_dir, config_path, output / 'controls', allow_single_source)
    data, data_hash = load(Path(data_dir) / 'dataset.json')
    if data_hash != controls['binding']['input_sha256']:
        raise DataBlocked('dataset changed between controls and H003')
    binding = dict(controls['binding'],
        source_sha256=source_hash(),
        h003_driver_sha256=digest(Path(__file__).read_bytes()),
        h003_signal_sha256=digest((root / 'leek/mean_reversion_signal.py').read_bytes()),
        data_issue_registry_sha256=digest((root / 'research/data_conflicts.json').read_bytes()),
        preregistration_sha256=digest((root / 'research/H003_PROTOCOL.md').read_bytes()),
        preregistration_commit=PREREGISTRATION_COMMIT)
    results = dict(controls['results'])
    candidate_reports = {}
    with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
        for case_name, cost in config['cost_cases'].items():
            key = case_name + '__' + MODEL_ID
            replay = simulate(data['bars'],data['dividends'],config,MODEL_ID,cost)
            candidate_reports[key] = replay
            results[key] = replay['summary']
    assessment = screen(results)
    report = dict(status='COMPLETED_H003_REAL_HISTORY_CONDITIONAL',
        evidence_grade=controls['evidence_grade'], binding=binding,
        audit=controls['audit'], protocol=config, results=results,
        assessment=assessment, sample_role='already_consumed_development_sample',
        source_reference='mementum/backtrader@b853d7c90b6721476eb5a5ea3135224e33db1f14',
        source_license='GPL-3.0-or-later; concept only, independent MIT implementation',
        automatic_promotion=False)
    for key, result in candidate_reports.items():
        atomic_create(output / (key + '.json'),
            dict(binding=binding, evidence_grade=controls['evidence_grade'],**result))
    atomic_create(output / 'experiment.json',report)
    print(json.dumps({'H003_ASSESSMENT':assessment,
        'evidence_grade':report['evidence_grade']},sort_keys=True))
    for key, summary in results.items():
        print(json.dumps({'H003_COMPARISON':key,**summary},sort_keys=True))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--allow-single-source',action='store_true')
    args = parser.parse_args()
    run(args.data_dir,args.output,args.fetch,args.allow_single_source)


if __name__ == '__main__':
    main()
