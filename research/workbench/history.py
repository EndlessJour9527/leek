"""Allowlisted public archival results, not a replay or a private-file adapter.

The pinned manifest anchors the frozen capsule. Its existing verifier checks
all eight accounting paths. Only selected derived fields cross into the UI.
"""
import gzip
import hashlib
import json
from pathlib import Path

from research.ca1_20261022 import verify_public
from research.workbench import experiment_report

CAPSULE = Path(__file__).resolve().parents[1] / 'ca1_20261022'
MANIFEST_SHA256 = '414c21f4756668b074d16197ddb29a91f7aead219cf8d1bc1f6ab816c6635ca9'
SOURCE_COMMIT = '764ed05b3d5da94c513a70f4f0098214d38ebd9e'
SOURCE_URL = f'https://github.com/EndlessJour9527/leek/blob/{SOURCE_COMMIT}/research/ca1_20261022/'
FIELDS = ('final_nav', 'total_return', 'cagr', 'mdd', 'fees', 'slippage',
          'no_fill', 'no_order', 'complete_round_trips', 'win_rate', 'mean_weights')


def load_experiment(ident, *, root=CAPSULE):
    if ident != 'ca1':
        raise ValueError('unknown experiment')
    root = Path(root)
    if root.is_symlink():
        raise ValueError('symlink capsule')
    manifest_bytes = (root / 'PUBLIC_MANIFEST.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise ValueError('unrecognized manifest')
    manifest = json.loads(manifest_bytes)
    # Reject symlinked parents too. No HTTP argument can select this root.
    for relative in [*manifest, 'PUBLIC_MANIFEST.json',
                     'verification_archive/v1/PUBLIC_MANIFEST.json',
                     'verification_archive/v1/verify_public.py.txt']:
        path = root / relative
        current = path
        while current != root:
            if current.is_symlink():
                raise ValueError('symlink evidence')
            current = current.parent
    verification = verify_public.verify(root)

    def read(relative):
        # Recheck exact bytes used by the adapter after verification; no cache
        # may carry a success forward when the evidence is missing or changed.
        data = (root / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest[relative]:
            raise ValueError('evidence changed')
        return verify_public.load_json(gzip.decompress(data) if relative.endswith('.gz') else data)

    summary = read('implementation/RESULTS/SUMMARY.json')
    attribution = read('implementation/READ_ONLY_ATTRIBUTION.json')['CA1_BASE']
    fixed = read('implementation/RESULTS/CA1_BASE_fixed_fill_double.json.gz')
    result = {
        'id': 'ca1', 'title': 'CA1 · 股债金月度配置', 'synthetic': False,
        'period': '2021-10-18 至 2026-06-30', 'sessions': 1140,
        'initial_capital': 50000, 'currency': 'CNY',
        'sample': 'ALL_SEEN_DEVELOPMENT',
        'label': '真实历史的公开派生账本；不是私人账户或新的回测结果',
        'limitations': ['全部已见开发数据，不是未见样本',
                        '已计交易费和滑点，未计固定研究费',
                        '私人原始输入未接入；未重验市场来源',
                        '真实可成交、停复牌、限价与容量未认证',
                        '基准不是同风险对照；不自动晋级或实盘'],
        'verification': verification, 'manifest_sha256': MANIFEST_SHA256,
        'source_commit': SOURCE_COMMIT,
        'decision': read('implementation/RESULTS/DECISION.json')['decision'],
        'accounts': {name: {key: row[key] for key in FIELDS}
                     for name, row in summary.items()},
        'research_cost': read('implementation/RESULTS/CA1_BASE_research_cost.json'),
        'research_cost_scenarios': {account: read(f'implementation/RESULTS/{account}_research_cost.json')
                                    for account in ('CA1_BASE', 'CA1_DOUBLE')},
        'fixed_fill_cost_diagnostic': {key: fixed[key] for key in ('label', 'final_nav', 'funding_deficit')},
        'attribution': attribution['assets'],
        'failed_orders': attribution['failed_orders'],
        'sources': [dict(id=ident, title=title, path=path, url=SOURCE_URL + path,
                         sha256=MANIFEST_SHA256 if ident == 'manifest' else manifest[path])
                    for ident, title, path in (
            ('registration', '实验登记：规则与成本假设', 'REGISTRATION_CA1.md'),
            ('results', '结果解释与限制', 'RESULTS.md'),
            ('summary', '全部账户与成本结果', 'implementation/RESULTS/SUMMARY.json'),
            ('attribution', '未成交与收益归因', 'implementation/READ_ONLY_ATTRIBUTION.json'),
            ('research_base', '基础账户研究费用情景', 'implementation/RESULTS/CA1_BASE_research_cost.json'),
            ('research_double', '双倍成本账户研究费用情景', 'implementation/RESULTS/CA1_DOUBLE_research_cost.json'),
            ('fixed_fill', '固定成交成本翻倍诊断（gzip JSON）', 'implementation/RESULTS/CA1_BASE_fixed_fill_double.json.gz'),
            ('manifest', '公开档案校验清单', 'PUBLIC_MANIFEST.json'))],
    }
    result['report'] = experiment_report.build(result)
    return result
