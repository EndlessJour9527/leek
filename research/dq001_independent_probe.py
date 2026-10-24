"""Read-only DQ001 third-provider probe; never repairs prices or runs strategies.

Yahoo quote OHLC is compared, never adjclose. Binary float serialization can
be mapped to a 0.001 grid only within 0.000001, with original tokens retained.
This is NOT tolerance for the 0.001 Eastmoney/Tencent disagreement. Matching
another distributor is evidence for review, not certified truth or independence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

D = Decimal
DATES = ('2020-08-21', '2020-08-24', '2020-08-25', '2020-08-26', '2020-08-27')
FIELDS = ('open', 'high', 'low', 'close')
TZ = ZoneInfo('Asia/Shanghai')
TICK = D('0.001')
SERIALIZATION_EPSILON = D('0.000001')
MAX_BYTES = 1_000_000


class EvidenceBlocked(ValueError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EvidenceBlocked('duplicate JSON field')
        result[key] = value
    return result


def load_json(raw: bytes):
    try:
        return json.loads(raw, parse_float=D, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EvidenceBlocked('nonfinite JSON')))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceBlocked('invalid JSON evidence') from exc


def price(value):
    if isinstance(value, bool) or not isinstance(value, (D, int, str)):
        raise EvidenceBlocked('missing or invalid quote value')
    try:
        text = str(value)
        if len(text) > 50:
            raise ValueError('unbounded value')
        number = D(text)
        if not number.is_finite() or not D('0') < number < D('1000000'):
            raise ValueError('price domain')
        grid = number.quantize(TICK, rounding=ROUND_HALF_EVEN)
    except (ValueError, InvalidOperation) as exc:
        raise EvidenceBlocked('invalid price') from exc
    distance = abs(number - grid)
    if distance > SERIALIZATION_EPSILON or grid <= 0:
        raise EvidenceBlocked('off-tick quote; no inferred price correction')
    return {'raw': text, 'tick_value': str(grid), 'serialization_distance': str(distance)}


def parse_quotes(raw: bytes):
    payload = load_json(raw)
    try:
        chart = payload['chart']
        if chart.get('error') is not None:
            raise EvidenceBlocked('provider returned an error')
        results = chart['result']
        if not isinstance(results, list) or len(results) != 1:
            raise EvidenceBlocked('expected one instrument result')
        result = results[0]
        meta = result['meta']
        if meta.get('symbol') != '510300.SS' or meta.get('currency') != 'CNY':
            raise EvidenceBlocked('instrument or currency mismatch')
        if meta.get('exchangeTimezoneName') != 'Asia/Shanghai':
            raise EvidenceBlocked('unexpected exchange timezone')
        stamps = result['timestamp']
        series = result['indicators']['quote']
        if not isinstance(stamps, list) or not isinstance(series, list) or len(series) != 1:
            raise EvidenceBlocked('quote vectors missing')
        quotes = series[0]
        if any(not isinstance(quotes.get(k), list) or len(quotes[k]) != len(stamps) for k in FIELDS):
            raise EvidenceBlocked('inconsistent vector lengths')
        days = {}
        for i, stamp in enumerate(stamps):
            if type(stamp) is not int:
                raise EvidenceBlocked('integer UTC timestamps required')
            day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(TZ).date().isoformat()
            if day not in DATES:
                continue
            if day in days:
                raise EvidenceBlocked('duplicate session')
            row = {k: price(quotes[k][i]) for k in FIELDS}
            v = {k: D(row[k]['tick_value']) for k in FIELDS}
            if not v['low'] <= min(v['open'], v['close']) <= max(v['open'], v['close']) <= v['high']:
                raise EvidenceBlocked('OHLC range invalid')
            days[day] = row
        if set(days) != set(DATES):
            raise EvidenceBlocked('incomplete disputed sessions')
        return {'meta': {k: meta.get(k) for k in ('symbol', 'currency', 'exchangeName', 'exchangeTimezoneName')},
                'rows': {day: days[day] for day in DATES},
                'price_semantics': 'indicators.quote OHLC; adjclose ignored; split-basis not independently certified'}
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, OSError) as exc:
        raise EvidenceBlocked('unsupported quote response shape') from exc


def compare(raw: bytes, reference: dict):
    if not isinstance(reference, dict):
        raise EvidenceBlocked('invalid reference object')
    if (reference.get('status') != 'SOURCE_CONFLICT'
            or reference.get('differing_cells') != 20 or reference.get('differences_resolved') is not False):
        raise EvidenceBlocked('expected unresolved DQ001 reference')
    mismatches = reference.get('mismatches')
    if not isinstance(mismatches, list) or len(mismatches) != 20:
        raise EvidenceBlocked('expected all twenty disputed cells')
    parsed = parse_quotes(raw)
    seen, comparisons = set(), []
    totals = {'matches_eastmoney_only': 0, 'matches_tencent_only': 0, 'matches_neither': 0}
    for cell in mismatches:
        try:
            key = (cell['date'], cell['field'])
            if key in seen or key[0] not in DATES or key[1] not in FIELDS:
                raise EvidenceBlocked('duplicate/unknown disputed cell')
            seen.add(key)
            em, tx = price(cell['eastmoney']), price(cell['tencent'])
            if D(em['serialization_distance']) != 0 or D(tx['serialization_distance']) != 0:
                raise EvidenceBlocked('reference must be exact tick prices')
            if D(em['tick_value']) - D(tx['tick_value']) != TICK:
                raise EvidenceBlocked('reference is not the registered one-tick conflict')
            third = parsed['rows'][key[0]][key[1]]
            tag = ('matches_eastmoney_only' if D(third['tick_value']) == D(em['tick_value']) else
                   'matches_tencent_only' if D(third['tick_value']) == D(tx['tick_value']) else 'matches_neither')
            totals[tag] += 1
            comparisons.append(dict(date=key[0], field=key[1], eastmoney=em['tick_value'],
                                    tencent=tx['tick_value'], yahoo=third, comparison=tag))
        except (KeyError, TypeError) as exc:
            raise EvidenceBlocked('malformed conflict reference') from exc
    if seen != {(day, k) for day in DATES for k in FIELDS}:
        raise EvidenceBlocked('not a complete 5-day OHLC comparison')
    return {'status': 'THIRD_PROVIDER_EVIDENCE_ONLY', 'counts': totals,
            'meta': parsed['meta'], 'price_semantics': parsed['price_semantics'],
            'comparisons': comparisons, 'dq001_resolved': False, 'automatic_promotion': False,
            'backtest_executed': False,
            'limitations': ['Distributor upstream independence unknown.',
                           'Agreement does not certify exchange-original prices or historic revisions.',
                           'No prices, strategy parameters, or data-conflict gates modified.']}


def probe_url():
    start = int(datetime(2020, 8, 21, tzinfo=TZ).timestamp())
    end = int(datetime(2020, 8, 28, tzinfo=TZ).timestamp())
    return 'https://query1.finance.yahoo.com/v8/finance/chart/510300.SS?' + urlencode({
        'period1': start, 'period2': end, 'interval': '1d', 'events': 'history'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', default='research/results/DQ001_source_audit.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error('refusing to overwrite evidence')
    ref_bytes = Path(args.reference).read_bytes()
    reference = load_json(ref_bytes)
    url = probe_url()
    report = {'status': 'THIRD_PROVIDER_UNAVAILABLE', 'requested_url': url,
              'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
              'reference_sha256': hashlib.sha256(ref_bytes).hexdigest(),
              'dq001_resolved': False, 'automatic_promotion': False, 'backtest_executed': False}
    try:
        req = Request(url, headers={'User-Agent': 'LeekResearchAudit/1.0', 'Accept': 'application/json'})
        with urlopen(req, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
            report['http_status'] = response.status
        if len(raw) > MAX_BYTES:
            raise EvidenceBlocked('response exceeds bounded audit size')
        report['response_sha256'] = hashlib.sha256(raw).hexdigest()
        report.update(compare(raw, reference))
    except HTTPError as exc:
        report.update(http_status=exc.code, reason='HTTP request rejected; no retries, cookies or bypass attempted')
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        report['reason'] = type(exc).__name__ + ': ' + str(exc)[:250]
    except EvidenceBlocked as exc:
        report.update(status='THIRD_PROVIDER_UNUSABLE', reason=str(exc))
    # Exclusive creation is atomic with respect to other writers. No raw dataset
    # is published, only provenance and twenty derived comparisons when present.
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    print(json.dumps(report, ensure_ascii=False))
    # Zero here means audit recorded (possibly failure), NOT successful backtest.


if __name__ == '__main__':
    main()
