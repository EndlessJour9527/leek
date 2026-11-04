"""Chinese explanation of verified derived evidence; no performance claims added."""
from decimal import Decimal
from html import escape

from research.workbench import history


def esc(value):
    return escape(str(value), quote=True)


def money(value):
    return format(Decimal(str(value)), ',.2f')


def pct(value):
    return format(Decimal(str(value)) * 100, '.3f') + '%'


def catalog():
    return '''<section id="experiments" class="panel"><h2>选择一个已完成的历史实验</h2>
<p>阅读已公开的实验归档，先看结论，再按层查看依据。不会重新运行历史交易。</p>
<a class="experiment-choice" href="/experiment?id=ca1#experiment">CA1 · 股债金月度配置 →</a>
<p class="muted">2021-10-18 至 2026-06-30 · 真实历史归档 · 已见开发样本 · 进入后核对档案</p>
<p>H002 / H003 的完整结果尚未接入此阅读入口，不用摘要代替档案。</p></section>'''


def explain_metric(metric, sources, key, summary='口径与来源', *, anchor=True):
    refs = ''.join(f'<li><a href="{esc(sources[ref["source_id"]]["url"])}" target="_blank" rel="noreferrer noopener">{esc(sources[ref["source_id"]]["title"])}</a>：<code>{esc(ref["selector"])}</code><br><small>文件 SHA-256：{sources[ref["source_id"]]["sha256"]}</small></li>' for ref in metric['sources'])
    ident = f' id="metric-{esc(key)}"' if anchor else ''
    return f'''<details class="metric-info"{ident}><summary>{esc(summary)}</summary>
<p>{esc(metric['definition'])}</p><p>期间：{esc(metric['period'])}；单位：{esc(metric['unit'])}。<br>口径：{esc(metric['basis'])}。</p>
<p>数值状态：{esc(metric['state_label'])}。</p>
<ul>{refs}</ul>{'<p>算式：<code>'+esc(metric['formula'])+'</code></p>' if metric['formula'] else ''}</details>'''


def render(ident):
    try:
        r = history.load_experiment(ident)
    except Exception:
        return '''<section id="experiment" class="panel"><h2>归档暂时无法核对</h2>
<p>资料缺失、版本改变或校验失败。本页暂不展示收益数字，原件未改动。</p>
<p>请维护者恢复完整源码内的公开 CA1 归档后刷新。合成示例仍可单独使用。</p>
<a href="/#experiments">返回选择实验</a></section>'''
    accounts = r['accounts']
    base, double = accounts['CA1_BASE'], accounts['CA1_DOUBLE']
    report = r['report']
    metrics = report['metrics']
    source_map = {s['id']: s for s in r['sources']}
    anchored = set()

    def value(key):
        metric = metrics[key]
        if metric['value'] is None:
            return metric['state_label']
        return pct(metric['value']) if metric['unit'] == 'RATIO' else money(metric['value'])

    def detail(key, summary=None):
        html = explain_metric(metrics[key], source_map, key, summary or value(key), anchor=key not in anchored)
        anchored.add(key)
        return html

    cards = ''
    for key in ('CA1_BASE.profit', 'CA1_BASE.research_fx7', 'CA1_BASE.economic_fx7', 'CA1_BASE.mdd'):
        metric = metrics[key]
        cards += f'<div class="result-card"><small>{esc(metric["label"])} · {"元" if metric["unit"] == "CNY" else "基础账户"}</small><strong>{value(key)}</strong><p>{esc(metric["definition"])}</p>{detail(key,"口径与来源")}</div>'
    states = ''.join(f'<li><strong>{esc(a["label"])}</strong><span class="badge {"good" if a["state"] == "VERIFIED" else "wait"}">{"已核对该项" if a["state"] == "VERIFIED" else "未验证 / 未认证"}</span><p>{esc(a["detail"])}</p></li>' for a in report['assurances'])
    steps = ''.join(f'<li><strong>{esc(g["title"])}</strong><p>{esc(g["impact"])} 完成条件：{esc(g["completion"])}</p></li>' for g in report['evidence_gaps'])
    rows = ''
    names = {'CA1': '股债金月度配置', 'SCASH': '约三分之一股票目标＋现金',
             'BH300': '沪深300 ETF 买入持有', 'CASH': '纯现金（不计息）'}
    for account, name in names.items():
        for cost, label in [('BASE', '基础成本'), ('DOUBLE', '双倍成本重执行')]:
            a = accounts[account + '_' + cost]
            prefix = account + '_' + cost
            rows += f'<tr><th scope="row">{name}<br><small>{label}</small></th><td>{detail(prefix+".final_nav")}</td><td>{detail(prefix+".cagr")}</td><td>{detail(prefix+".mdd")}</td></tr>'
    failures = ''.join(f'<tr><td>{esc(o["execute"])}</td><td>{esc(o["symbol"])}</td><td>卖出 {o["quantity"]} 份</td><td>模型未成交，成交 0 份</td></tr>' for o in r['failed_orders'])
    sources = ''.join(f'<li><a href="{esc(s["url"])}" target="_blank" rel="noreferrer noopener">{esc(s["title"])} ↗</a></li>' for s in r['sources'])
    expenses = ''.join(f'<tr><th scope="row">固定汇率 {fx} 元/美元</th><td>{detail(f"CA1_BASE.research_fx{fx}")}</td><td>{detail(f"CA1_BASE.economic_fx{fx}")}</td><td>{detail(f"CA1_DOUBLE.economic_fx{fx}")}</td></tr>' for fx in (6, 7, 8))
    concentration = value('CA1_BASE.gold_profit_share')
    return f'''<section id="experiment" class="panel result">
<div class="eyebrow">真实历史归档 · 公开派生账本已核对 · 非真实账户</div>
<h2>{esc(r['title'])}：这次研究说明了什么？</h2>
<p class="notice"><strong>结论：{esc(report['conclusion']['title'])}。</strong>{esc(report['conclusion']['reason'])}</p>
<p>{r['period']} · {r['sessions']:,} 个交易日 · 每个账户起始模拟本金 {money(r['initial_capital'])} 元。
全部是已见开发样本，没有真正未见验证。</p>
<div id="experiment-overview"><h3>先看收益、全部成本情景和风险</h3>
<p>研究问题：把现金换成国债和黄金，并按月调整，是否优于相同股票目标权重的股票＋现金组合？</p>
<div class="overview-metrics">{cards}</div>
<p>期末模拟总资产 {money(base['final_nav'])} 元，并非全部变现。上方研究费按固定汇率7估算，
是通用费用假设，不是私人订阅披露。初始本金与期末资产相减得到盈利，不能把期末资产全叫收益。</p>
<p>基础手续费 {money(base['fees'])} 元、滑点 {money(base['slippage'])} 元已计入资产。黄金贡献约 {concentration} 的盈利；真实可成交仍未认证。</p>
<div class="scroll"><table><caption>CA1 交易成本情景 · 元 · 均未扣独立研究费</caption><thead><tr><th>情景</th><th>期末模拟资产</th><th>含义</th></tr></thead><tbody>
<tr><th>基础成本</th><td>{money(base['final_nav'])}</td><td>冻结模型账户</td></tr>
<tr><th>双倍成本重新执行</th><td>{money(double['final_nav'])}</td><td>重新计算订单和资金路径</td></tr>
<tr><th>固定成交成本翻倍</th><td>{detail('fixed_fill.final_nav')}</td><td>反事实诊断，不可执行；资金未出现负值也不等于可以交易</td></tr>
</tbody></table></div>
<p>独立研究费：每月100美元全额归本项目，按含首尾 {report['research_fee_basis']['calendar_days_inclusive']} 个自然日 ÷ 365.25 折算。
不是从账本逐日扣款，以下<strong>不是复投年化</strong>，也不使用当前汇率。</p>
<div class="scroll"><table><caption>独立研究费用情景 · 元 · 盈利减费用后的经济结余</caption><thead><tr><th>固定汇率假设</th><th>区间研究费</th><th>基础账户经济结余</th><th>双倍重执行经济结余</th></tr></thead><tbody>{expenses}</tbody></table></div>
<p><strong>下一步：</strong>先补真实成交证据并制定独立验证方案；<a href="#history-evidence">查看缺口与完成条件 ↓</a></p>
<details><summary>这些“已核对”分别验证了什么？</summary><p>{esc(report['operation']['label'])}；{esc(report['data_source']['label'])}。</p><ul class="assurances">{states}</ul></details>
</div>
<nav class="layer-nav" aria-label="实验分层阅读"><a href="#history-data">数据与规则</a><a href="#history-result">结果与成本</a><a href="#history-benchmark">基准</a><a href="#history-risk">风险与执行</a><a href="#history-evidence">证据</a></nav>
<article id="history-data" class="layer"><h3>1 · 数据与策略层：研究了什么？</h3>
<p>股票（510300 沪深300 ETF）、国债（511010）、黄金（518880）各以三分之一为目标，按月调整。
月末产生信号，之后先卖后买；按 100 份整数单位交易，现金分红不自动再投。</p>
<p>目标等权不等于实际每天等权：基础模型平均股票 / 国债 / 黄金市值占总资产约
{pct(base['mean_weights']['510300'])} / {pct(base['mean_weights']['511010'])} / {pct(base['mean_weights']['518880'])}，其余为现金或应收款。</p>
<p>本入口只接入公开派生账本。私人原始行情尚未接入，未在此重验市场来源；公司价值分析也不属于这个资产配置实验。</p></article>
<article id="history-result" class="layer"><h3>2 · 账本与评估层：赚了多少，花了多少？</h3>
<p>点击数字查看与导出一致的定义、期间、单位、成本口径、数值状态及来源字段。</p>
<div class="grid three"><div><h4>期末模拟总资产 · 元</h4>{detail('CA1_BASE.final_nav')}</div><div><h4>年化收益</h4>{detail('CA1_BASE.cagr')}</div><div><h4>手续费 · 元</h4>{detail('CA1_BASE.fees')}</div><div><h4>滑点 · 元</h4>{detail('CA1_BASE.slippage')}</div><div><h4>双倍重执行手续费 · 元</h4>{detail('CA1_DOUBLE.fees')}</div><div><h4>双倍重执行滑点 · 元</h4>{detail('CA1_DOUBLE.slippage')}</div></div></article>
<article id="history-benchmark" class="layer"><h3>3 · 基准层：比什么更好？</h3>
<p>同一窗口、相同起始本金，保留全部四类账户和两种成本。股票＋现金用于对照股票目标权重，
<strong>不是同风险对照</strong>；结果差异不能直接叫独立投资能力。</p>
<div class="scroll"><table><caption>成本后结果 · 不含固定研究费</caption><thead><tr><th>账户 / 成本</th><th>期末资产（元）</th><th>年化收益</th><th>最大回撤</th></tr></thead><tbody>{rows}</tbody></table></div></article>
<article id="history-risk" class="layer"><h3>4 · 风险与模拟执行层：哪里可能失真？</h3>
<p><strong>最大回撤 {pct(base['mdd'])}</strong>：模拟总资产从此前最高点到随后低点的最大跌幅，
不是最大单笔亏损，也不是未来损失上限。</p>
<p>黄金贡献基础盈利的约 {concentration}。这是事后会计归因，提示收益集中，不能推断以后继续有效。</p>{detail('CA1_BASE.gold_profit_share', '盈利集中度的口径与来源')}
<p>基础账户有 {base['no_fill']} 笔模型未成交、{base['no_order']} 次未形成订单（例如整数份额或预算约束），两者不同。
下列卖单触及模型价格边界，被保留为未成交，没有补卖。这不等于交易所已确认当时无法卖出。</p>
<div class="scroll"><table><caption>基础账户的模型未成交记录</caption><thead><tr><th>执行日期</th><th>ETF代码</th><th>计划操作</th><th>结果</th></tr></thead><tbody>{failures}</tbody></table></div>
<p>其他模型成交采用开盘代理价及足量成交假设。官方逐日限价、停复牌和竞价排队 / 容量证据仍不完整。</p>
<p>完整买入后再全部清仓的样本为 {base['complete_round_trips']}，所以胜率<strong>未定义</strong>，不是 0% 胜率。部分卖出不能冒充完整交易。</p>{detail('CA1_BASE.win_rate')}
<p>扣研究费后的复投年化：尚未计算，本情景不构造此指标。</p>{detail('CA1_BASE.after_research_fee_cagr', '为什么这里不是0%？')}</article>
<article id="history-evidence" class="layer"><h3>5 · 证据层：这些数字可信到什么程度？</h3>
<p>{esc(report['operation']['label'])}；{esc(report['data_source']['label'])}。</p><ul class="assurances">{states}</ul>
<h4>下一步：证据缺口与完成条件</h4><ol>{steps}</ol>
<details><summary>查看逐项来源与版本，供复核使用</summary><ul>{sources}</ul>
<p>来源固定在公开提交 {r['source_commit']}。本机归档与固定清单一致；不是实时研究更新。</p>
<pre>清单 SHA-256：{r['manifest_sha256']}\n归档结论：{esc(r['decision'])}</pre></details>
<p><a href="/experiment-export?id=ca1">导出本页核对结果与来源（JSON）</a> · <a href="/#experiments">返回选择实验</a></p>
</article></section>'''
