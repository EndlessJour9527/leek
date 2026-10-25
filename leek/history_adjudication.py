"""Exact, reviewed DQ001 source precedence, never a price tolerance.

The public review binds a small factual extract, not a private vendor panel.
Runtime hashes establish artifact integrity, not reviewer authentication: the
noncircular evidence commit and independent review are established in Git review.
No disagreement outside the frozen twenty cells can be adjudicated here.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from .contract import DataBlocked
from .replay import canonical, digest, load

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = 'research/results/DQ001_source_audit.json'
AUDIT_SHA256 = 'c4790fd5fff383b959b732b02af7172c24eb6c72187d72fb34e61eaab213e763'
EVIDENCE_PATH = 'research/results/DQ001_exchange_evidence.json'
REVIEW_PATH = 'research/reviews/DQ001_source_precedence_review.json'
# Trusted activation follows the preceding evidence commit and independent source review.
EVIDENCE_SHA256 = 'b0abbe0e470c1db379958de754dfa3ec75414c98ca45254143e4ba043289dfc9'
REVIEW_SHA256 = 'd2227a6fdc3430627e119805c58e5c384913d49d202be4683624f4b01442bcf4'
EVIDENCE_COMMIT = '94173048588fa6c1d8c4d7ff0c6c8bba32365c6e'
POLICY = 'SSE_OFFICIAL_OHLC_FOR_EXACT_DQ001_CELLS'
STATUS = 'REVIEWED_SOURCE_PRECEDENCE'
GRADE = 'REVIEWED_EXCHANGE_SOURCE_PRECEDENCE_CONDITIONAL'
DATES = ('2020-08-21', '2020-08-24', '2020-08-25', '2020-08-26', '2020-08-27')
FIELDS = ('open', 'close', 'high', 'low')


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _read_bound(root, relative, expected):
    if not _sha(expected):
        raise DataBlocked('DQ001 invalid evidence SHA256')
    path = Path(root) / relative
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise DataBlocked('DQ001 evidence path is not local and regular')
    try:
        value, actual = load(path)
    except (OSError, ValueError, TypeError) as exc:
        raise DataBlocked('DQ001 bound evidence unavailable') from exc
    if actual != expected:
        raise DataBlocked('DQ001 evidence hash changed')
    return value


def load_resolution(record):
    """Validate both immutable conflict and hash-bound independent adjudication."""
    try:
        if record.get('evidence_path') != EVIDENCE_PATH or record.get('review_path') != REVIEW_PATH:
            raise DataBlocked('DQ001 reviewed artifact paths missing or changed')
        if (record.get('evidence_sha256') != EVIDENCE_SHA256
                or record.get('review_sha256') != REVIEW_SHA256
                or record.get('review_commit') != EVIDENCE_COMMIT):
            raise DataBlocked('DQ001 unrecognized reviewed artifact binding')
        audit = _read_bound(ROOT, AUDIT_PATH, AUDIT_SHA256)
        evidence = _read_bound(ROOT, EVIDENCE_PATH, record.get('evidence_sha256'))
        review = _read_bound(ROOT, REVIEW_PATH, record.get('review_sha256'))
        if (evidence.get('version') != 'DQ001.exchange-evidence.v1'
                or evidence.get('instrument') != '510300'
                or evidence.get('original_audit_sha256') != AUDIT_SHA256):
            raise DataBlocked('DQ001 exchange evidence identity changed')
        source = evidence['source']
        url = urlparse(source['url'])
        if (url.scheme != 'https' or url.hostname != 'yunhq.sse.com.cn'
                or url.path != '/v1/sh1/dayk/510300' or not _sha(source.get('sha256'))):
            raise DataBlocked('DQ001 official source provenance missing')
        expected = {(c['date'], c['field']): c for c in audit['mismatches']}
        if set(expected) != {(d, f) for d in DATES for f in FIELDS} or len(audit['mismatches']) != 20:
            raise DataBlocked('DQ001 original twenty-cell scope changed')
        cells = evidence['cells']
        if not isinstance(cells, list) or len(cells) != 20:
            raise DataBlocked('DQ001 exchange evidence needs all twenty cells')
        seen = set()
        for cell in cells:
            key = (cell['date'], cell['field'])
            if key in seen or key not in expected:
                raise DataBlocked('DQ001 duplicate or unknown reviewed cell')
            seen.add(key)
            original = expected[key]
            for vendor in ('eastmoney', 'tencent'):
                if cell[vendor] != original[vendor]:
                    raise DataBlocked('DQ001 original disputed quote changed')
            if not isinstance(cell['sse'], str) or Decimal(cell['sse']) != Decimal(original['tencent']):
                raise DataBlocked('DQ001 exchange quote does not select the reviewed price')
        required_checks = ('official_source_identity', 'field_mapping', 'bounded_unadjusted_basis_supported',
                           'all_twenty_cells', 'original_audit_preserved')
        if (review.get('version') != 'DQ001.source-review.v1'
                or review.get('status') != 'PASS_REVIEWED_SOURCE_PRECEDENCE'
                or review.get('policy') != POLICY
                or review.get('review_commit') != record['review_commit']
                or review.get('evidence_sha256') != record['evidence_sha256']
                or review.get('original_audit_sha256') != AUDIT_SHA256
                or any(review.get('checks', {}).get(k) is not True for k in required_checks)):
            raise DataBlocked('DQ001 independent review binding or semantics incomplete')
        return {'cells': expected, 'binding': {
            'policy': POLICY, 'review_commit': record['review_commit'],
            'evidence_sha256': record['evidence_sha256'], 'review_sha256': record['review_sha256'],
            'original_audit_sha256': AUDIT_SHA256}}
    except (KeyError, TypeError, AttributeError, ValueError, ArithmeticError) as exc:
        raise DataBlocked('DQ001 malformed reviewed source evidence') from exc


def selected_cells(bars, resolution):
    """Even single-source or formerly matching datasets must contain accepted cells."""
    lookup = {bar['date']: bar for bar in bars}
    for (day, field), cell in resolution['cells'].items():
        if day not in lookup or Decimal(lookup[day][field]) != Decimal(cell['tencent']):
            raise DataBlocked('DQ001 selected quote missing or changed; new review required')


def adjudicate(eastmoney, tencent, resolution):
    from .history_data import validate_bars
    validate_bars(eastmoney); validate_bars(tencent)
    if [b['date'] for b in eastmoney] != [b['date'] for b in tencent]:
        raise DataBlocked('cross-provider session mismatch')
    selected = deepcopy(eastmoney)
    seen = set()
    for em, tx, out in zip(eastmoney, tencent, selected):
        for field in FIELDS:
            key = (em['date'], field)
            if key in resolution['cells']:
                old = resolution['cells'][key]
                if (Decimal(em[field]) != Decimal(old['eastmoney'])
                        or Decimal(tx[field]) != Decimal(old['tencent'])):
                    raise DataBlocked('DQ001 current provider quote changed; new review required')
                seen.add(key)
                out[field] = old['tencent']
            elif Decimal(em[field]) != Decimal(tx[field]):
                raise DataBlocked('unreviewed cross-provider OHLC disagreement')
    if seen != set(resolution['cells']):
        raise DataBlocked('DQ001 incomplete current twenty-cell coverage')
    selected_cells(selected, resolution)
    return selected, dict(status=STATUS, sessions=len(selected), ohlc_cells=4 * len(selected),
        differing_cells=20, resolved_cells=20, unresolved_cells=0, volume_compared=False,
        primary_vendor='Eastmoney except exact reviewed OHLC cells from SSE-corroborated Tencent',
        normalized_bars_sha256=digest(canonical(selected)), **resolution['binding'])


def snapshot_bindings(raw_dir, eastmoney_name, tencent_names):
    """Only relative, immutable price-file descriptors enter public derived metadata."""
    def descriptor(name):
        if Path(name).name != name:
            raise DataBlocked('invalid price snapshot name')
        return {'name': name, 'sha256': digest((Path(raw_dir) / name).read_bytes())}
    return {'eastmoney': [descriptor(eastmoney_name)],
            'tencent': [descriptor(name) for name in tencent_names]}


def verify_reviewed_dataset(data, data_dir, config, resolution):
    """Reparse hash-checked raw sources and reproduce *all* selected bars before use."""
    from .history_data import parse_eastmoney, parse_tencent, parse_dividends, DIVIDEND_URL
    try:
        quality = data['metadata']['crosscheck']
        snapshots = quality['source_snapshots']
        if set(snapshots) != {'eastmoney', 'tencent'} or len(snapshots['eastmoney']) != 1:
            raise DataBlocked('reviewed dataset price snapshots missing')
        raw_dir = Path(data_dir) / 'raw'
        if raw_dir.is_symlink():
            raise DataBlocked('price snapshot symlink rejected')
        seen = set()
        provenance = data['metadata']['sources']
        if not isinstance(provenance, list):
            raise DataBlocked('reviewed source provenance missing')
        def read(item, vendor, year=None):
            name = item['name']
            if (not isinstance(name, str) or Path(name).name != name or name in seen
                    or not _sha(item.get('sha256'))):
                raise DataBlocked('invalid or duplicate price snapshot binding')
            seen.add(name)
            path = raw_dir / name
            if path.is_symlink() or not path.resolve().is_relative_to(raw_dir.resolve()):
                raise DataBlocked('price snapshot path escapes archive')
            raw = path.read_bytes()
            if digest(raw) != item['sha256']:
                raise DataBlocked('reviewed raw source hash changed')
            matches = [s for s in provenance if isinstance(s, dict) and s.get('snapshot_name') == name]
            if (len(matches) != 1 or matches[0].get('sha256') != item['sha256']
                    or matches[0].get('bytes') != len(raw)):
                raise DataBlocked('reviewed source provenance hash mismatch')
            source_url = urlparse(matches[0]['url']); query = parse_qs(source_url.query)
            if source_url.scheme != 'https':
                raise DataBlocked('reviewed source URL must use HTTPS')
            if vendor == 'eastmoney':
                expected_query = dict(secid='1.510300', klt='101', fqt='0',
                    beg=config['warmup_start'].replace('-', ''), end=config['evaluation_end'].replace('-', ''))
                if (source_url.hostname != 'push2his.eastmoney.com'
                        or source_url.path != '/api/qt/stock/kline/get'
                        or any(query.get(k) != [v] for k, v in expected_query.items())):
                    raise DataBlocked('reviewed Eastmoney source identity/adjustment changed')
            elif vendor == 'dividends':
                if matches[0]['url'] != DIVIDEND_URL:
                    raise DataBlocked('reviewed distribution source identity changed')
            elif (source_url.hostname != 'web.ifzq.gtimg.cn'
                    or source_url.path != '/appstock/app/fqkline/get'
                    or query.get('param') != [f'sh510300,day,{year}-01-01,{year}-12-31,640,']):
                raise DataBlocked('reviewed Tencent source identity/adjustment changed')
            return raw
        em = parse_eastmoney(read(snapshots['eastmoney'][0], 'eastmoney'))
        tx = []
        years = list(range(int(config['warmup_start'][:4]), int(config['evaluation_end'][:4]) + 1))
        if len(snapshots['tencent']) != len(years):
            raise DataBlocked('incomplete reviewed Tencent source years')
        for year, item in zip(years, snapshots['tencent']):
            tx.extend(b for b in parse_tencent(read(item, 'tencent', year)) if b['date'][:4] == str(year))
        first, last = config['warmup_start'], config['evaluation_end']
        em = [b for b in em if first <= b['date'] <= last]
        tx = [b for b in tx if first <= b['date'] <= last]
        bars, expected = adjudicate(em, tx, resolution)
        expected['source_snapshots'] = snapshots
        if quality != expected or data['bars'] != bars:
            raise DataBlocked('reviewed normalized dataset or provenance changed')
        distributions = [s for s in provenance if isinstance(s, dict) and s.get('url') == DIVIDEND_URL]
        if len(distributions) != 1:
            raise DataBlocked('reviewed distribution snapshot missing or ambiguous')
        descriptor = dict(name=distributions[0]['snapshot_name'], sha256=distributions[0]['sha256'])
        events = parse_dividends(read(descriptor, 'dividends'), first, last)
        if data['dividends'] != events:
            raise DataBlocked('reviewed distribution dataset changed')
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DataBlocked('reviewed dataset source replay failed') from exc
    return GRADE


def reconcile_sources(eastmoney, tencent, raw_dir, eastmoney_name, tencent_names):
    from .history_review_gate import require_history_review
    resolution = require_history_review()
    bars, quality = adjudicate(eastmoney, tencent, resolution)
    quality['source_snapshots'] = snapshot_bindings(raw_dir, eastmoney_name, tencent_names)
    return bars, quality


def validate_dataset_evidence(data, data_dir, config, allow_single_source=False):
    from .history_review_gate import require_history_review
    from .history_data import validate_bars
    resolution = require_history_review()
    if not isinstance(data, dict) or not isinstance(data.get('metadata'), dict):
        raise DataBlocked('reviewed dataset metadata missing')
    validate_bars(data.get('bars'))
    selected_cells(data['bars'], resolution)
    quality = data['metadata'].get('crosscheck', {})
    if not isinstance(quality, dict):
        raise DataBlocked('reviewed dataset crosscheck must be an object')
    if quality.get('status') == STATUS:
        return verify_reviewed_dataset(data, data_dir, config, resolution)
    raise DataBlocked('DQ001 requires replayable two-source reviewed evidence; legacy grade cannot bypass it')
