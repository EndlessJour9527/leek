"""ML002 data-only preflight: bounded three-ETF SSE/Tencent OHLC, not a backtest.

No strategy fitting, returns, raw-source publication, account aggregation, or
relaxed reconciliation. Uses only Python stdlib; source conflict is a blocker.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

UNIVERSE = {'510300': 'broad_equity', '511010': 'government_bond', '518880': 'gold'}
YEARS = range(2019, 2026)
PERIOD = ('2019-01-01', '2025-12-31')
FIELDS = ('open', 'high', 'low', 'close')
RESEARCH_CAPITAL = Decimal('50000')
ENTRY_BUDGET = Decimal('0.20')
RESEARCH_LOT = 100
LIMIT = 5_000_000

class Blocked(ValueError):
    pass


def _decimal(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise Blocked('invalid numeric quote') from e
    if not d.is_finite() or not Decimal('0') < d < Decimal('1000000'):
        raise Blocked('out-of-range quote')
    return d


def _normalize(rows):
    result = {}
    for d, values in rows:
        if not isinstance(d, str) or len(d) != 10:
            raise Blocked('invalid session date')
        try:
            if date.fromisoformat(d).isoformat() != d:
                raise ValueError()
        except ValueError as e:
            raise Blocked('invalid session date') from e
        if d in result:
            raise Blocked('duplicate session')
        if set(values) != set(FIELDS):
            raise Blocked('incomplete OHLC')
        q = {k: _decimal(values[k]) for k in FIELDS}
        if q['low'] > min(q['open'], q['close'], q['high']) or q['high'] < max(q['open'], q['close'], q['low']):
            raise Blocked('invalid high-low relationship')
        result[d] = q
    if not result or list(result) != sorted(result):
        raise Blocked('empty or unordered sessions')
    return result


def parse_sse(raw, symbol):
    try:
        doc = json.loads(raw, parse_float=Decimal)
        if not isinstance(doc, dict) or str(doc['code']) != symbol or not isinstance(doc['kline'], list):
            raise Blocked('SSE identity/schema disagreement')
        rows = []
        for r in doc['kline']:
            if not isinstance(r, list) or len(r) not in (6, 7):
                raise Blocked('SSE kline schema changed')
            s = str(r[0])
            if len(s) != 8 or not s.isdigit():
                raise Blocked('SSE date token invalid')
            d = f'{s[:4]}-{s[4:6]}-{s[6:]}'
            if PERIOD[0] <= d <= PERIOD[1]:
                rows.append((d, dict(zip(FIELDS, r[1:5]))))
        return _normalize(rows)
    except (KeyError, TypeError, ValueError, UnicodeError) as e:
        if isinstance(e, Blocked):
            raise
        raise Blocked('SSE JSON unusable') from e


def parse_tencent(raw, symbol, year):
    try:
        payload = json.loads(raw, parse_float=Decimal)
        rows = payload['data']['sh' + symbol]['day']
        if not isinstance(rows, list):
            raise Blocked('Tencent rows missing')
        selected = []
        for r in rows:
            if not isinstance(r, list) or len(r) < 6:
                raise Blocked('Tencent row schema changed')
            d = r[0]
            if isinstance(d, str) and PERIOD[0] <= d <= PERIOD[1]:
                if not d.startswith(str(year)):
                    raise Blocked('Tencent response crosses requested year')
                selected.append((d, {'open': r[1], 'high': r[3], 'low': r[4], 'close': r[2]}))
        return _normalize(selected)
    except (KeyError, TypeError, ValueError, UnicodeError) as e:
        if isinstance(e, Blocked):
            raise
        raise Blocked('Tencent JSON unusable') from e


def compare_prices(sse, tx, calendar):
    s, t, c = set(sse), set(tx), set(calendar)
    mismatches = [(d, f) for d in sorted(s & t) for f in FIELDS if sse[d][f] != tx[d][f]]
    sessions = len(s & t)
    lots = [p['open'] * RESEARCH_LOT for p in sse.values()]
    cash_budget = RESEARCH_CAPITAL * ENTRY_BUDGET
    result = {
        'sse_sessions': len(s), 'tencent_sessions': len(t), 'matched_session_count': sessions,
        'sse_missing_vs_calendar': len(c - s), 'sse_extra_vs_calendar': len(s - c),
        'tencent_missing_vs_calendar': len(c - t), 'tencent_extra_vs_calendar': len(t - c),
        'differing_ohlc_cells': len(mismatches), 'differing_session_count': len({d for d, _ in mismatches}),
        'difference_preview': [{'date': d, 'field': f} for d, f in mismatches[:10]],
        'assumed_100_unit_lot_min_cost': str(min(lots)),
        'assumed_100_unit_lot_max_cost': str(max(lots)),
        'sessions_affordable_at_fixed_reference_budget': sum(x <= cash_budget for x in lots),
        'reference_budget_cny': str(cash_budget),
        'lot_assumption_only_not_broker_contract': True,
    }
    result['prices_feasible'] = s == t == c and not mismatches
    result['lot_always_exceeds_reference_budget'] = min(lots) > cash_budget
    return result


def url_sse(symbol):
    return f'https://yunhq.sse.com.cn:32042/v1/sh1/dayk/{symbol}?begin=-2500&end=-1&period=day'


def url_tx(symbol, year):
    return f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh{symbol},day,{year}-01-01,{year}-12-31,640,'


def request_once(url):
    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Leek-ML002-Research/1.0'})
    with urlopen(req, timeout=18) as response:
        if response.status != 200:
            raise Blocked('non-200 source response')
        raw = response.read(LIMIT + 1)
    if not raw or len(raw) > LIMIT:
        raise Blocked('source body outside bounded size')
    return raw


def probe():
    provenance = []
    def get(origin, name, url):
        raw = request_once(url)
        provenance.append({'origin': origin, 'route': name, 'url': url,
                           'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)})
        return raw

    cal = []
    for year in YEARS:
        raw = get('Tencent', f'calendar-{year}', url_tx('000001', year))
        payload = json.loads(raw)
        try:
            rows = payload['data']['sh000001']['day']
            if not isinstance(rows, list) or not rows:
                raise Blocked('index calendar missing')
            new = [r[0] for r in rows]
            if any(not isinstance(d, str) or not d.startswith(str(year)) for d in new):
                raise Blocked('calendar wrong year')
        except (KeyError, TypeError, ValueError) as e:
            raise Blocked('invalid index calendar') from e
        cal.extend(new)
    if len(cal) != len(set(cal)) or cal != sorted(cal):
        raise Blocked('calendar duplicate/unsorted')
    if {str(y) for y in YEARS} != set(Counter(d[:4] for d in cal)) or len(cal) < 1500:
        raise Blocked('calendar years incomplete')

    results = {}
    for symbol, exposure in UNIVERSE.items():
        try:
            sse = parse_sse(get('SSE', symbol, url_sse(symbol)), symbol)
            tx = {}
            for year in YEARS:
                new = parse_tencent(get('Tencent', f'{symbol}-{year}', url_tx(symbol, year)), symbol, year)
                if set(tx) & set(new):
                    raise Blocked('repeated Tencent year sessions')
                tx.update(new)
            tx = dict(sorted(tx.items()))
            results[symbol] = {'exposure': exposure, **compare_prices(sse, tx, cal)}
        except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
            results[symbol] = {'exposure': exposure, 'prices_feasible': False,
                               'blocker_type': type(exc).__name__, 'blocker': str(exc)[:160]}
    all_prices = len(results) == len(UNIVERSE) and all(x['prices_feasible'] for x in results.values())
    return {'status': 'PRICE_FEASIBILITY_ONLY_CA_BLOCKED' if all_prices else 'BLOCKED_PRICE_PANEL',
            'calendar_sessions': len(cal), 'per_asset': results, 'source_hashes': provenance}


def main():
    report = {
        'schema': 'ML002_MULTI_ASSET_FEASIBILITY_V1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'symbols_fixed_before_fetch': UNIVERSE,
        'period': list(PERIOD), 'sample_role': 'SEEN_DEVELOPMENT',
        'historical_trade_runs': 0, 'new_models': 0, 'automatic_promotion': False,
        'corporate_actions_verified': False, 'point_in_time_certified': False,
        'risk_comparable_benchmark_implemented': False, 'trainable': False,
        'raw_quotes_published': False,
        'next_gate': 'fund-specific record/ex/pay dividends; splits; trading calendars; share-lot affordability; risk-matched benchmark',
    }
    try:
        report.update(probe())
    except (Blocked, ValueError, OSError, KeyError, TypeError) as e:
        report.update(status='BLOCKED_SOURCE_ACCESS_OR_SCHEMA', blocker_type=type(e).__name__,
                      blocker=str(e)[:160])
    directory = Path(os.environ.get('RUNNER_TEMP', '/tmp'))
    path = directory/'ml002-multi-etf-feasibility.json'
    path.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': report['status'], 'per_asset': report.get('per_asset'),
                      'blocker': report.get('blocker'), 'trade_runs': 0, 'trainable': False},
                     ensure_ascii=False, sort_keys=True))
    return 0 if report['status'] == 'PRICE_FEASIBILITY_ONLY_CA_BLOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
