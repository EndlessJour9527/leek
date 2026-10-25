"""Persistent data-review gate shared by historical performance entrypoints.

A declared resolution is an auditable record, not exchange certification.
This module never changes the registry or treats vendor voting as approval.
Read-only data acquisition remains available to investigate blocked issues.
"""
from pathlib import Path
import re

from .contract import DataBlocked
from .replay import load

REGISTRY_PATH = Path(__file__).resolve().parents[1] / 'research/data_conflicts.json'


def require_history_review(registry=None):
    """Reject before market-data reads; return the validated bounded resolution."""
    if registry is None:
        try:
            registry, _ = load(REGISTRY_PATH)
        except (OSError, ValueError, TypeError) as exc:
            raise DataBlocked('missing or malformed historical data-conflict registry') from exc
    if not isinstance(registry, dict) or registry.get('version') != 'data-conflicts.v1':
        raise DataBlocked('invalid historical data-conflict registry')
    issues = registry.get('issues')
    if not isinstance(issues, list) or any(not isinstance(x, dict) for x in issues):
        raise DataBlocked('invalid historical data-conflict issues')
    matching = [x for x in issues if x.get('id') == 'DQ001']
    if len(matching) != 1 or matching[0].get('status') != 'RESOLVED_REVIEWED':
        raise DataBlocked('DQ001 unresolved or ambiguous; reviewed evidence required')
    record = matching[0].get('resolution')
    if not isinstance(record, dict):
        raise DataBlocked('DQ001 reviewed resolution record missing')
    commit = record.get('review_commit')
    urls = record.get('evidence_urls')
    rationale = record.get('rationale')
    if (not isinstance(commit, str) or re.fullmatch('[0-9a-f]{40}', commit) is None
            or not isinstance(urls, list) or not urls
            or any(not isinstance(u, str) or not u.startswith('https://') for u in urls)
            or not isinstance(rationale, str) or not rationale.strip()):
        raise DataBlocked('DQ001 reviewed resolution evidence malformed')
    from .history_adjudication import load_resolution
    return load_resolution(record)
