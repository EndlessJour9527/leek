"""Presentation wrapper for one frozen experiment; never alters replay/v1 data."""
from decimal import Decimal


def build(archive):
    period = archive['period']
    metrics = {}

    def add(key, label, value, unit, definition, basis, refs, *, formula=None, state='AVAILABLE'):
        metrics[key] = dict(label=label, value=None if value is None else str(value),
                            unit=unit, period=period, definition=definition, basis=basis,
                            sources=[dict(source_id=s, selector=p) for s, p in refs],
                            state=state, formula=formula,
                            state_label={
                                'AVAILABLE': '已有数值',
                                'UNDEFINED_NO_COMPLETE_TRADES': '未定义：无完整清仓样本',
                                'NOT_COMPUTED': '尚未计算：本情景不构造此指标',
                                'INSUFFICIENT_DATA': '资料不足：不能计算',
                            }[state])

    account_definitions = (
        ('final_nav', '期末模拟总资产', 'CNY', '本金加累计损益，包含仍持仓资产的估值，未全部变现。'),
        ('cagr', '年化收益', 'RATIO', '把整个区间折算成年复合增速，不代表每年都赚这么多。'),
        ('mdd', '最大回撤', 'RATIO', '总资产从此前最高点到随后低点的最大跌幅，不是最大单笔亏损或未来损失上限。'),
        ('fees', '手续费', 'CNY', '模型累计收取的交易费用，已计入期末资产，不再重复扣除。'),
        ('slippage', '滑点', 'CNY', '模型成交价格相对参考价格的不利偏差，已计入期末资产，不再重复扣除。'),
        ('win_rate', '完整交易胜率', 'RATIO', '没有买入后再全部清仓的完整样本，胜率未定义；不是零胜率。'),
    )
    for account, row in archive['accounts'].items():
        basis = ('基础交易成本' if account.endswith('_BASE') else '双倍交易成本重新执行') + '；不含固定研究费'
        for field, label, unit, definition in account_definitions:
            add(account + '.' + field, label, row[field], unit, definition, basis,
                [('summary', f'/{account}/{field}')],
                state='UNDEFINED_NO_COMPLETE_TRADES' if field == 'win_rate' else 'AVAILABLE')
        add(account + '.profit', '累计模拟盈利', Decimal(str(row['final_nav'])) - archive['initial_capital'],
            'CNY', '期末资产减起始本金；已扣交易费用和滑点，未扣独立研究费。', basis,
            [('summary', f'/{account}/final_nav'), ('registration', 'L11-L12: initial capital')],
            formula='final_nav - initial_capital')

    for account, scenarios in archive['research_cost_scenarios'].items():
        for i, row in enumerate(scenarios):
            fx = row['fx_scenario']
            basis = f'{account}；每月100美元全部归本项目；固定汇率{fx}元/美元；账外独立情景'
            source_id = 'research_base' if account == 'CA1_BASE' else 'research_double'
            add(f'{account}.research_fx{fx}', '区间研究费', row['expense'], 'CNY',
                '按含首尾自然日折算费用；不是已从交易账户扣款，也不是当前汇率。', basis,
                [(source_id, f'/{i}/expense'), ('registration', 'section 7: research subscription cost')],
                formula='round_cent(1200 * 1717 / 365.25 * fixed_fx)')
            add(f'{account}.economic_fx{fx}', '盈利减研究费', row['terminal_surplus'], 'CNY',
                '交易成本后盈利再减独立研究费；不是复投年化或扣费后可执行账户。', basis,
                [(source_id, f'/{i}/terminal_surplus'), ('summary', f'/{account}/final_nav')],
                formula='final_nav - 50000 - research_expense')

    fixed = archive['fixed_fill_cost_diagnostic']
    add('fixed_fill.final_nav', '固定成交成本翻倍 · 反事实资产', fixed['final_nav'], 'CNY',
        '保持基础成交不变，仅增加费用；不可执行，不能与双倍成本重新执行混为一谈。',
        '账外成本敏感性诊断；不含固定研究费', [('fixed_fill', '/final_nav'), ('fixed_fill', '/label')])
    gold_index, gold = next((i, a) for i, a in enumerate(archive['attribution']) if a['symbol'] == '518880')
    add('CA1_BASE.gold_profit_share', '黄金盈利贡献比例',
        Decimal(gold['net_profit_contribution']) / Decimal(metrics['CA1_BASE.profit']['value']),
        'RATIO', '这段样本中黄金对盈利的事后会计贡献，提示收益集中，不能预测未来。',
        '基础交易成本后盈利归因；不含独立研究费',
        [('attribution', f'/CA1_BASE/assets/{gold_index}/net_profit_contribution'), ('summary', '/CA1_BASE/final_nav')],
        formula='gold_net_profit_contribution / (final_nav - 50000)')
    add('CA1_BASE.after_research_fee_cagr', '扣研究费后的复投年化', None, 'RATIO',
        '研究费没有逐日进入交易账本，本报告不构造扣费后复投年化；不能用经济结余伪造。',
        '账外独立费用情景；尚未计算，而非零收益或胜率未定义',
        [('registration', 'section 7: no fabricated reinvested NAV/CAGR')], state='NOT_COMPUTED')
    return dict(
        schema_version='leek.workbench.report/1',
        operation=dict(value='READ_ARCHIVE', label='读取已完成归档，未重跑回测'),
        data_source=dict(value='REAL_OBSERVATION_DERIVED', label='真实历史的公开派生账本；非真实账户'),
        sample_usage=dict(value=archive['sample'], label='全部已见开发样本'),
        assurances=[
            dict(id='file_integrity', state='VERIFIED', label='公开文件完整性', detail='已核对固定清单中的文件哈希。'),
            dict(id='ledger_identity', state='VERIFIED', label='派生账本资产加总', detail='已核对8条账户路径共9,120行恒等式；不证明市场来源。'),
            dict(id='market_data', state='NOT_VERIFIED_HERE', label='市场数据真实性', detail='原始输入尚未接入；本入口未重验行情来源。'),
            dict(id='unseen_sample', state='NOT_VALIDATED', label='未见样本验证', detail='全部数据已用于开发；没有真正未见验证。'),
            dict(id='execution', state='NOT_CERTIFIED', label='真实成交认证', detail='开盘代理与足量成交是假设；限价、停复牌和竞价容量未认证。'),
        ],
        metrics=metrics,
        research_fee_basis=dict(monthly_usd=100, calendar_days_inclusive=1717,
                                annual_day_basis='365.25', fixed_fx_scenarios=[6, 7, 8],
                                charged_to_ledger=False, after_fee_cagr_computed=False),
        conclusion=dict(value=archive['decision'], title='保留继续研究，还不能据此实盘',
                        reason='模型内有盈利，但研究费情景下经济结余为负，且未见样本和真实成交证据不足。'),
        evidence_gaps=[
            dict(id='execution', title='补齐真实成交证据', state='OPEN',
                 impact='模型成交与未成交不能直接当成交易所实际结果。',
                 completion='逐项核验对应日期的官方限价、交易状态和竞价容量，并保留出处。'),
            dict(id='validation', title='取得独立验证', state='OPEN',
                 impact='重复阅读同一开发样本不会增加独立证据。',
                 completion='另行登记未见窗口或前瞻验证方案；本页不新增策略阈值或启动回放。'),
        ],
    )
