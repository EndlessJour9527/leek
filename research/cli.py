"""Explicit research status/preflight/run and hash-bound private CA1 restoration.

No background service, approval generation, or automatic data-conflict override.
Exit 0: report-only/ready/completed; 2: blocked; 1: error. Read the JSON status,
not just CI color. Preflight never downloads market data or computes returns.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from leek.contract import DataBlocked, validate_calendar
from leek.history_review_gate import require_history_review
from leek.history_data import VERSION, validate_bars
from leek.replay import load

ROOT = Path(__file__).resolve().parents[1]
CAPSULE = ROOT / 'research/ca1_20261022'
CA1_MANIFEST_SHA = 'ad513ba95ff9ab5e08b0240ec3afdce295f16b5a8197117e9733f26c5e0f0ff0'
CA1_RELEASE_SHA = '51f6887a7f6e3c9b4e6741b979f8eb48e83c26e28d99d5bd1f1a0a5cb2573acd'
EXPERIMENTS = {
    'h002': ('research/run_h002.py', 'research/H002_PROTOCOL.md', 'leek/channel_signal.py'),
    'h003': ('research/run_h003.py', 'research/H003_PROTOCOL.md', 'leek/mean_reversion_signal.py'),
    'ca1': ('research/ca1_20261022/implementation/run_batch.py',),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def result(status, experiment=None, **fields):
    return dict(schema='research-operations.v1', status=status, experiment=experiment,
                automatic_promotion=False, new_independent_market_evidence=False,
                historical_replays_completed=0, **fields)


def bound_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError('archive path escapes its root')
    part = path
    while part != root:
        if part.is_symlink():
            raise ValueError('archive symlink is not permitted')
        part = part.parent
    return path


def ca1_requirements():
    manifest = CAPSULE / 'implementation/IMPLEMENTATION_MANIFEST.json'
    release_path = CAPSULE / 'implementation/RUN_RELEASE.json'
    if sha(manifest) != CA1_MANIFEST_SHA or sha(release_path) != CA1_RELEASE_SHA:
        raise ValueError('archived release binding changed; register a new version')
    release = json.loads(release_path.read_bytes())
    if release['status'] != 'RUN_RELEASE' or release['manifest_sha256'] != CA1_MANIFEST_SHA:
        raise ValueError('invalid original release')
    requirements = {'implementation/IMPLEMENTATION_MANIFEST.json': CA1_MANIFEST_SHA,
                    'implementation/RUN_RELEASE.json': CA1_RELEASE_SHA}
    for name, expected in json.loads(manifest.read_bytes()).items():
        relative = os.path.normpath('implementation/' + name)
        bound_path(CAPSULE, relative)
        requirements[relative] = expected
    for name, expected in release['evidence'].items():
        bound_path(CAPSULE, name)
        if name in requirements and requirements[name] != expected:
            raise ValueError('conflicting original evidence hashes')
        requirements[name] = expected
    return requirements


def preflight(experiment, data_dir=None, private_root=None, fetch=False, allow_single_source=False):
    if experiment not in EXPERIMENTS:
        raise ValueError('unknown experiment')
    if sys.flags.optimize:
        return result('BLOCKED_RUNTIME', experiment, reasons=['historical engines require nonoptimized Python'])
    if experiment == 'ca1':
        root = Path(private_root) if private_root else CAPSULE
        missing, mismatched = [], []
        for name, expected in ca1_requirements().items():
            path = bound_path(root, name)
            if not path.is_file(): missing.append(name)
            elif sha(path) != expected: mismatched.append(name)
        status = 'BLOCKED_INPUTS' if missing or mismatched else 'READY_FOR_ARCHIVE_REPLAY'
        return result(status, experiment, missing=missing, mismatched=mismatched,
                      reproduction_scope='frozen already-seen archive; not new independent evidence')
    # Gate precedes ALL market input reads, network and output construction.
    try:
        require_history_review()
    except DataBlocked as exc:
        return result('BLOCKED_DATA', experiment, reasons=[str(exc)], data_conflicts=['DQ001'])
    from research.run_h002 import BASE_CONFIG_SHA256
    from leek.real_backtest import checked_config
    config, config_sha = load(ROOT / 'research/real_history_protocol.json')
    checked_config(config)
    if config_sha != BASE_CONFIG_SHA256:
        return result('BLOCKED_CONFIG', experiment, reasons=['frozen baseline configuration changed'])
    if fetch:
        if data_dir is None or Path(data_dir).exists():
            return result('BLOCKED_INPUTS', experiment, reasons=['fetch needs a new, absent data directory'])
        return result('READY_FOR_ACQUISITION', experiment, dataset_verified=False)
    if data_dir is None or not (Path(data_dir) / 'dataset.json').is_file():
        return result('BLOCKED_INPUTS', experiment, missing=['dataset.json'])
    try:
        from research.run_real_history import evidence_allowed
        data, input_sha = load(Path(data_dir) / 'dataset.json')
        if (data['version'] != VERSION or data['synthetic'] is not False
                or data['adjustment'] != 'raw' or data['instrument'] != '510300'
                or data['metadata']['config_sha256'] != config_sha):
            raise DataBlocked('dataset identity/config binding mismatch')
        validate_bars(data['bars']); validate_calendar(data['calendar'])
        if data['calendar'] != [row['date'] for row in data['bars']]:
            raise DataBlocked('calendar alignment mismatch')
        grade = evidence_allowed(data['metadata'], allow_single_source)
    except (DataBlocked, ValueError, KeyError, TypeError) as exc:
        return result('BLOCKED_INPUTS', experiment, reasons=[type(exc).__name__ + ': input validation failed'])
    return result('READY_FOR_CONDITIONAL_RESEARCH', experiment, input_sha256=input_sha,
                  evidence_grade=grade, dataset_verified=False,
                  note='structural checks only; existing runner performs final accounting validation')


def status():
    team = json.loads((ROOT / 'research/trader_team.json').read_bytes())
    lanes = []
    for name, paths in EXPERIMENTS.items():
        missing = [p for p in paths if not (ROOT / p).is_file()]
        lanes.append(dict(experiment=name, implementation='MISSING' if missing else 'IMPLEMENTED',
                          missing_code=missing, readiness=preflight(name)))
    return result('STATUS_REPORT_ONLY', lanes=lanes, seats=team['seats'],
                  archived_decisions={'AG1': 'STOP_RESEARCH_VARIANT',
                                      'CA1': 'RETAIN_FOR_FURTHER_EVIDENCE'})


def restore_ca1(source, destination):
    """Copy only exact lawful originals to a NEW private workspace; no fabrication."""
    check = preflight('ca1', private_root=source)
    if check['status'] != 'READY_FOR_ARCHIVE_REPLAY':
        return check
    dest = Path(destination).resolve()
    if dest.is_relative_to(ROOT.resolve()) or dest.exists():
        raise ValueError('destination must be new and outside the repository')
    dest.mkdir(mode=0o700)  # exclusive: existing user directory is never modified
    try:
        shutil.copytree(CAPSULE, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ca1_requirements():
            target = bound_path(dest, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bound_path(Path(source), name), target)
        verified = preflight('ca1', private_root=dest)
        if verified['status'] != 'READY_FOR_ARCHIVE_REPLAY':
            raise ValueError('private archive changed during restoration')
    except Exception:
        shutil.rmtree(dest)  # only the directory exclusively created above
        raise
    return result('RESTORED_PRIVATE_INPUTS', 'ca1', files_verified=len(ca1_requirements()),
                  note='No historical replay executed; original release and economic code unchanged')


def run_experiment(experiment, output, data_dir=None, private_root=None, fetch=False,
                   allow_single_source=False):
    check = preflight(experiment, data_dir, private_root, fetch, allow_single_source)
    if not check['status'].startswith('READY_'):
        return check
    output = Path(output).resolve()
    if output.exists(): raise ValueError('refuse existing output')
    if experiment == 'ca1':
        private = Path(private_root).resolve() if private_root else CAPSULE
        if private.is_relative_to(ROOT.resolve()) or output.is_relative_to(ROOT.resolve()):
            return result('BLOCKED_INPUTS', experiment, reasons=['CA1 replay needs a restored private workspace outside repository'])
        command = [sys.executable, str(private / 'implementation/run_batch.py'),
                   '--release', str(private / 'implementation/RUN_RELEASE.json'), '--output', str(output)]
        completed = subprocess.run(command, cwd=private / 'implementation', capture_output=True, timeout=180)
        if completed.returncode:
            return result('FAILED', experiment, reasons=['archived runner rejected execution'],
                          partial_outputs=output.exists())
        report = result('COMPLETED_ARCHIVE_REPLAY', experiment, sample_role='ALL_SEEN_DEVELOPMENT')
    else:
        from research import run_h002, run_h003
        runner = run_h002.run if experiment == 'h002' else run_h003.run
        try:
            # Original drivers print extensive diagnostics; keep summary JSON separate.
            with contextlib.redirect_stdout(io.StringIO()):
                original = runner(data_dir, output, fetch, allow_single_source)
        except DataBlocked as exc:
            return result('BLOCKED_DATA', experiment, reasons=[str(exc)], partial_outputs=output.exists())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return result('FAILED', experiment, reasons=[type(exc).__name__], partial_outputs=output.exists())
        report = result('COMPLETED_CONDITIONAL_RESEARCH', experiment,
                        evidence_grade=original['evidence_grade'], assessment=original['assessment'],
                        binding=original['binding'], sample_role='already_consumed_development_sample')
    report['historical_replays_completed'] = 1
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'preflight', 'run', 'restore-ca1'))
    parser.add_argument('--experiment', choices=tuple(EXPERIMENTS))
    parser.add_argument('--data-dir'); parser.add_argument('--private-root')
    parser.add_argument('--output'); parser.add_argument('--report')
    parser.add_argument('--source'); parser.add_argument('--destination')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--allow-single-source', action='store_true')
    args = parser.parse_args(argv)
    if args.report and Path(args.report).exists():
        parser.error('report already exists; refusing overwrite before execution')
    if args.command in ('preflight', 'run') and not args.experiment:
        parser.error('--experiment is required')
    if args.command == 'run' and not args.output: parser.error('--output is required')
    if args.command == 'restore-ca1' and not (args.source and args.destination):
        parser.error('--source and --destination are required')
    try:
        if args.command == 'status':
            report = status()
        elif args.command == 'restore-ca1':
            report = restore_ca1(args.source, args.destination)
        elif args.command == 'preflight':
            report = preflight(args.experiment, args.data_dir, args.private_root, args.fetch, args.allow_single_source)
        else:
            report = run_experiment(args.experiment, args.output, args.data_dir, args.private_root,
                                    args.fetch, args.allow_single_source)
    except Exception as exc:
        report = result('FAILED', args.experiment, reasons=[type(exc).__name__ + ': operation rejected'])
    report['operations_source_sha256'] = sha(__file__)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.report:
        with Path(args.report).open('x', encoding='utf-8') as handle:
            handle.write(text)
    print(text, end='')
    return 2 if report['status'].startswith('BLOCKED_') else 1 if report['status'] == 'FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
