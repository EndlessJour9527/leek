"""Version 2 public-evidence validator. No asserts; safe with -O/-OO.

Checks hashes and derived accounting, NOT a market replay, source certificate,
or trading authorization. Original v1 verifier/manifest remain in the archive.
"""
from datetime import date
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
V1_MANIFEST_SHA256 = '8ffbde8799c8703e169ee6401822e1a1c379305c27325d183d47a6cd942b443c'
ACCOUNTS = ('CA1', 'SCASH', 'BH300', 'CASH')
COSTS = ('BASE', 'DOUBLE')


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def load_json(raw):
    return json.loads(raw, object_pairs_hook=unique_pairs)


def safe_path(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute(), 'invalid manifest path')
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()), 'manifest path escapes capsule')
    require(path.is_file() and not path.is_symlink(), 'missing/nonregular manifest file: ' + relative)
    return path


def amount(value):
    require(isinstance(value, str) and len(value) < 100, 'decimal text required')
    result = Decimal(value)
    require(result.is_finite(), 'nonfinite accounting value')
    return result


def verify_account(report):
    """Semantic checks remain active even in optimized Python."""
    require(isinstance(report, dict), 'invalid account report')
    daily = report.get('daily')
    require(isinstance(daily, list) and len(daily) == 1140, 'unexpected daily row count')
    require(daily[0]['date'] == '2021-10-18' and daily[-1]['date'] == '2026-06-30', 'wrong sample bounds')
    previous = ''
    for row in daily:
        day = row['date']
        require(date.fromisoformat(day).isoformat() == day and day > previous, 'invalid/repeated session')
        previous = day
        positions = row['positions']
        require(set(positions) == {'510300', '511010', '518880'}, 'unexpected position universe')
        require(all('close' not in p for p in positions.values()), 'raw marks in public report')
        with localcontext() as context:
            context.prec = 64
            total = amount(row['cash']) + amount(row['receivable'])
            total += sum((amount(p['value']) for p in positions.values()), Decimal(0))
            require(amount(row['nav']) == total, 'NAV identity failed on ' + day)
    require(report.get('round_trips') == [], 'unexpected round-trip attribution')
    return len(daily)


def verify(root=ROOT):
    root = Path(root)
    archived = root / 'verification_archive/v1/PUBLIC_MANIFEST.json'
    require(sha(archived) == V1_MANIFEST_SHA256, 'original manifest archive changed')
    original = load_json(archived.read_bytes())
    require(sha(root / 'verification_archive/v1/verify_public.py.txt') == original['verify_public.py'],
            'original verifier archive changed')
    current = load_json((root / 'PUBLIC_MANIFEST.json').read_bytes())
    require(isinstance(current, dict) and set(current) == set(original), 'public manifest entries changed')
    for path, expected in current.items():
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) is not None,
                'invalid expected hash')
        if path != 'verify_public.py':
            require(expected == original[path], 'frozen evidence hash changed: ' + path)
        require(sha(safe_path(root, path)) == expected, 'hash mismatch: ' + path)
    rows = 0
    for account in ACCOUNTS:
        for cost in COSTS:
            path = root / 'implementation/RESULTS' / f'{account}_{cost}.json.gz'
            report = load_json(gzip.decompress(path.read_bytes()))
            require(report['account'] == account, 'account label mismatch')
            rows += verify_account(report)
    decision = load_json((root / 'implementation/RESULTS/DECISION.json').read_bytes())
    require(decision.get('decision') == 'RETAIN_FOR_FURTHER_EVIDENCE', 'fixed decision changed')
    return {'validator_version': 2, 'paths': 8, 'nav_rows': rows,
            'status': 'VERIFIED_DERIVED_EVIDENCE', 'historical_replay': False,
            'automatic_promotion': False}


def main():
    try:
        result = verify()
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, EOFError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        return 1
    print('PASS: public hashes and 9120 derived NAV rows; NOT full historical replay')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
