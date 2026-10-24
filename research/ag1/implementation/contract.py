"""Fail-closed helpers; qualification values must be supplied, never inferred."""
import hashlib
from datetime import date
from pathlib import Path
from ledger import dec

class DataBlocked(ValueError):
    pass

def iso_date(value):
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise DataBlocked('invalid ISO date')
    return value

def verify_pins(root, pins):
    root = Path(root).resolve()
    if not pins:
        raise DataBlocked('no frozen input hashes')
    for row in pins:
        p = (root / row['path']).resolve()
        if not p.is_relative_to(root):
            raise DataBlocked('input path escapes bundle')
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
            raise DataBlocked('missing or changed input: ' + row['path'])

def validate_calendar(sessions):
    for d in sessions: iso_date(d)
    if not sessions or sessions != sorted(set(sessions)):
        raise DataBlocked('empty, duplicate or unordered calendar')

def require_pool(expected_symbols, actual_symbols, qualifications):
    if len(expected_symbols) != len(set(expected_symbols)) or set(expected_symbols) != set(actual_symbols):
        raise DataBlocked('fixed universe mismatch')
    for symbol in expected_symbols:
        q = qualifications.get(symbol, {})
        for field in ('history_qualified', 'corporate_actions_qualified', 'calendar_qualified', 'tax_qualified'):
            if q.get(field) is not True:
                raise DataBlocked(symbol + ': ' + field)

def validate_raw_bar(bar):
    iso_date(bar['date'])
    try:
        o,h,l,c=(dec(bar[k]) for k in ('open','high','low','close'))
        if min(o,h,l,c)<=0 or not(l <= min(o,c) <= max(o,c) <= h):
            raise ValueError()
    except (KeyError, ValueError, ArithmeticError, TypeError):
        raise DataBlocked('missing, nonfinite or invalid OHLC')

def require_observation(rows_by_date, session, symbol):
    if session not in rows_by_date:
        raise DataBlocked(symbol + ': missing observation on ' + session)
    bar = rows_by_date[session]
    if bar.get('date') != session:
        raise DataBlocked('observation date mismatch')
    validate_raw_bar(bar)
    return bar
