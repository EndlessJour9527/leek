"""Conservative coverage helpers. No trading, pricing or execution certification."""
from datetime import date
import hashlib
from pathlib import Path
import re

UNKNOWN = 'UNKNOWN'

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def canonical_date(value):
    require(type(value) is str, 'date must be string')
    require(date.fromisoformat(value).isoformat() == value, 'noncanonical date')
    return value

def availability(published, signal, execute):
    for value in (published, signal, execute):
        canonical_date(value)
    require(signal < execute, 'signal must precede execution')
    if published < signal:
        return 'BEFORE_SIGNAL_DATE_ONLY_EOD_CONVENTION'
    if published == signal:
        return 'SAME_SIGNAL_DAY_CLOSE_TIME_UNCERTAIN'
    if published < execute:
        return 'AFTER_SIGNAL_BEFORE_EXECUTION_DATE'
    if published == execute:
        return 'EXECUTION_DAY_EOD_NOT_KNOWN_AT_OPEN'
    return 'FUTURE_TO_ORDER_RETROSPECTIVE_ONLY'

def verify_pins(root, supplied, expected):
    """Expected pins are supplied by a separately frozen experiment contract.

    This generic helper cannot establish that the caller preregistered them.
    It checks bytes, not source authenticity or semantic correctness.
    """
    require(type(expected) is dict and bool(expected), 'nonempty frozen pins required')
    require(type(supplied) is dict and supplied == expected, 'complete fixed pin set required')
    root = Path(root).resolve()
    for name, digest in expected.items():
        require(type(name) is str and name and not Path(name).is_absolute(), 'relative input name required')
        require('..' not in Path(name).parts, 'parent traversal')
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'SHA256 required')
        path = (root / name).resolve()
        require(root in path.parents, 'input outside root')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'input hash mismatch')

def coverage(orders, expected_ids):
    """Map already normalized identities only; intentionally accepts no prices.

    Expected identities belong to the external frozen contract. No private CA1
    order list is distributed. Changing that contract is not verified here.
    Repeated security/day across separate model accounts retains each identity.
    No incoming evidence label can promote this inventory to certification.
    """
    require(type(orders) is list and bool(orders), 'nonempty orders required')
    require(type(expected_ids) is list and bool(expected_ids), 'expected identities required')
    require(all(type(x) is str and x for x in expected_ids), 'identity strings required')
    require(len(expected_ids) == len(set(expected_ids)), 'duplicate expected identity')
    result, seen = [], set()
    fields = {'order_id', 'symbol', 'signal', 'execute', 'status'}
    for order in orders:
        require(type(order) is dict and set(order) == fields, 'normalized order fields required')
        identity = order['order_id']
        require(type(identity) is str and identity and identity not in seen, 'duplicate or invalid order identity')
        seen.add(identity)
        require(type(order['symbol']) is str and bool(order['symbol']), 'symbol required')
        require(order['status'] in ('FILL', 'NO_FILL', 'NO_ORDER'), 'invalid order status')
        require(canonical_date(order['signal']) < canonical_date(order['execute']), 'signal must precede execution')
        result.append(dict(order, applicable_rule_version=UNKNOWN,
                           direct_security_day_halt_resumption=UNKNOWN,
                           official_reference_and_daily_limits=UNKNOWN,
                           opening_timestamp_proof=UNKNOWN, opening_capacity_proof=UNKNOWN,
                           execution_certified=False))
    require(seen == set(expected_ids), 'incomplete or unexpected order coverage')
    return result
