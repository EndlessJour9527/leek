"""Run the registered ML001 pilot. Real-data gates precede all model fitting."""
from __future__ import annotations
import argparse
from copy import deepcopy
from decimal import Context, ROUND_HALF_UP, localcontext
from hashlib import sha256
import json
from pathlib import Path
import sys
import subprocess

from leek.contract import DataBlocked
from leek.real_backtest import simulate,checked_config
from .data import encoded,fetch_panel,load_panel

REGISTRATION_COMMIT='40b3690617cad922fa0d4f6053c14ae28448b332'
ROOT=Path(__file__).resolve().parents[2]


def screen(metrics,accounts):
    decisions={}
    for name in ('ridge','lightgbm'):
        checks={'predictive_mse_beats_zero':metrics[name]['mse']<metrics['zero']['mse'],
                'predictive_mse_beats_train_mean':metrics[name]['mse']<metrics['train_mean']['mse']}
        for case in ('base','stress'):
            m=accounts[case+'__'+name];hold=accounts[case+'__buy_hold'];ma=accounts[case+'__ma120_weekly']
            checks[case+'_net_beats_passive']=m['total_return_pct']>hold['total_return_pct']
            checks[case+'_net_beats_weekly_ma']=m['total_return_pct']>ma['total_return_pct']
            checks[case+'_drawdown_not_worse_than_passive']=m['max_close_drawdown_pct']>=hold['max_close_drawdown_pct']
            checks[case+'_at_least_20_closed_trades']=m['closed_trades']>=20
        decisions[name]=dict(decision='NEEDS_INDEPENDENT_VALIDATION' if all(checks.values()) else 'REJECTED_FOR_PROMOTION',
                             checks=checks,automatic_promotion=False)
    return decisions


def execute(input_directory,output_directory,fetch=False):
    if not __debug__:raise DataBlocked('historical economic engine requires nonoptimized Python')
    from .train import fit_predict,policies,EVALUATION_START,predictive_metrics
    root=Path(output_directory)
    if root.exists():raise DataBlocked('refuse existing output; preserve previous attempts')
    root.mkdir(parents=True)
    try:
        panel=fetch_panel(input_directory) if fetch else load_panel(input_directory)
        if panel.get('synthetic') is not False:raise DataBlocked('no synthetic fallback')
        config=json.loads((ROOT/'research/real_history_protocol.json').read_text());checked_config(config)
        config=deepcopy(config);config['evaluation_start']=EVALUATION_START
        git_sha=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
        binding=dict(execution_commit=git_sha or 'SOURCE_ARCHIVE',registration_commit=REGISTRATION_COMMIT,
                     protocol_sha256=sha256((Path(__file__).parent/'PROTOCOL.md').read_bytes()).hexdigest(),
                     input_sha256=sha256((Path(input_directory)/'dataset.json').read_bytes()).hexdigest(),
                     code_sha256={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(__file__).parent.glob('*.py'))},
                     engine_sha256=sha256((ROOT/'leek/real_backtest.py').read_bytes()).hexdigest())
        prediction,levels=fit_predict(panel['bars'],panel['dividends'],root/'models')
        states,dates=policies(panel['bars'],prediction['records'],levels)
        # Archive forecasts before interpreting account returns. No raw features/prices/labels published.
        public_records=[{k:v for k,v in r.items() if k!='target'} for r in prediction['records']]
        (root/'predictions.json').write_bytes(encoded(public_records))
        (root/'folds.json').write_bytes(encoded(prediction['folds']))
        accounts={}
        with localcontext(Context(prec=64,rounding=ROUND_HALF_UP)):
            for cost_name,cost in config['cost_cases'].items():
                for name in ('cash','buy_hold','ma120_weekly','ridge','lightgbm'):
                    strategy=name if name in ('cash','buy_hold') else 'ml001_frozen_policy'
                    kw={} if name in ('cash','buy_hold') else {'external_states':states[name]}
                    result=simulate(panel['bars'],panel['dividends'],config,strategy,cost,**kw)
                    result['summary']['policy_name']=name
                    key=cost_name+'__'+name;accounts[key]=result['summary']
                    (root/(key+'.json')).write_bytes(encoded(dict(binding=binding,**result)))
        weekly_records=[r for r in prediction['records'] if r['signal_date'] in set(dates)]
        report=dict(status='COMPLETED_CONDITIONAL_ML_RESEARCH',stage='ML-PILOT-01',binding=binding,
            sample_role='SEEN_DEVELOPMENT_CHRONOLOGICAL_OUT_OF_TRAINING_NOT_UNTOUCHED_HOLDOUT',
            data_audit=panel['audit'],sources=panel['provenance'],
            bars=len(panel['bars']),first=panel['calendar'][0],last=panel['calendar'][-1],
            dividend_events=len(panel['dividends']),folds=prediction['folds'],versions=prediction['versions'],
            learned_models=8,feature_count=16,prediction_rows=len(prediction['records']),
            decision_count=len(dates),predictive_metrics=prediction['metrics'],
            decision_date_metrics=predictive_metrics(weekly_records),accounts=accounts,
            decisions=screen(prediction['metrics'],accounts),automatic_promotion=False,broker_orders=False,
            constraints=['Single ETF, not a cross-sectional ranker or multi-asset validation',
                         'Overlapping 5-session labels are dependent; daily prediction count is not independent samples',
                         'Existing historical windows already consumed by project; not genuine forward evidence',
                         'Nominal source observations are retrospective; full CA and actual execution certification absent',
                         '20% entry budget is a reference, not a hard opening-gap or daily exposure cap',
                         'No terminal liquidation or future closing costs; open PnL remains in NAV',
                         'Cash rate zero; fees are frozen research assumptions, not actual broker tariffs',
                         'No statistical-significance or stable-profit claim from passing pilot screen'])
        (root/'summary.json').write_bytes(encoded(report))
        (root/'RUN_STATUS.json').write_bytes(encoded({'status':report['status'],'trained_models':8,
            'backtest_executed':True,'automatic_promotion':False}))
        print(json.dumps({'status':report['status'],'bars':report['bars'],
            'learned_models':8,'folds':len(report['folds']),'accounts':accounts,'decisions':report['decisions']},sort_keys=True))
        return report
    except Exception as exc:
        # Do not mislabel missing dependencies/programming errors as market-data failure.
        status='BLOCKED_DATA' if isinstance(exc,(DataBlocked,OSError)) else 'FAILED'
        (root/'RUN_STATUS.json').write_bytes(encoded({'status':status,'error_type':type(exc).__name__,
            'message':str(exc)[:800],'backtest_executed':False,'automatic_promotion':False}))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--fetch',action='store_true');args=parser.parse_args()
    execute(args.input_dir,args.output,args.fetch)


if __name__=='__main__':main()
