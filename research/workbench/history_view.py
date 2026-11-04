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
    profit = Decimal(str(base['final_nav'])) - r['initial_capital']
    rows = ''
    names = {'CA1': '股债金月度配置', 'SCASH': '约三分之一股票目标＋现金',
             'BH300': '沪深300 ETF 买入持有', 'CASH': '纯现金（不计息）'}
    for account, name in names.items():
        for cost, label in [('BASE', '基础成本'), ('DOUBLE', '双倍成本重执行')]:
            a = accounts[account + '_' + cost]
            rows += f'<tr><th scope="row">{name}<br><small>{label}</small></th><td>{money(a["final_nav"])}</td><td>{pct(a["cagr"])}</td><td>{pct(a["mdd"])}</td></tr>'
    failures = ''.join(f'<tr><td>{esc(o["execute"])}</td><td>{esc(o["symbol"])}</td><td>卖出 {o["quantity"]} 份</td><td>模型未成交，成交 0 份</td></tr>' for o in r['failed_orders'])
    sources = ''.join(f'<li><a href="{esc(s["url"])}" target="_blank" rel="noreferrer noopener">{esc(s["title"])} ↗</a></li>' for s in r['sources'])
    expenses = ''.join(f'<tr><th scope="row">1美元＝{c["fx_scenario"]}元</th><td>{money(c["expense"])}</td><td>{money(c["terminal_surplus"])}</td></tr>' for c in r['research_cost'])
    gold = next(a for a in r['attribution'] if a['symbol'] == '518880')
    concentration = pct(Decimal(gold['net_profit_contribution']) / profit)
    return f'''<section id="experiment" class="panel result">
<div class="eyebrow">真实历史归档 · 公开派生账本已核对 · 非真实账户</div>
<h2>{esc(r['title'])}：这次研究说明了什么？</h2>
<p class="notice"><strong>结论：保留继续研究，还不能据此实盘。</strong>在这段历史与模型假设下有盈利，
但收益集中于黄金、真实成交证据不完整，且固定研究费用可能抵消盈利。此页读取既有结果，没有重跑回测。</p>
<p>{r['period']} · {r['sessions']:,} 个交易日 · 每个账户起始模拟本金 {money(r['initial_capital'])} 元。
全部是已见开发样本，没有真正未见验证。</p>
<nav class="layer-nav" aria-label="实验分层阅读"><a href="#history-data">数据与规则</a><a href="#history-result">结果与成本</a><a href="#history-benchmark">基准</a><a href="#history-risk">风险与执行</a><a href="#history-evidence">证据</a></nav>
<article id="history-data" class="layer"><h3>1 · 数据与策略层：研究了什么？</h3>
<p>股票（510300 沪深300 ETF）、国债（511010）、黄金（518880）各以三分之一为目标，按月调整。
月末产生信号，之后先卖后买；按 100 份整数单位交易，现金分红不自动再投。</p>
<p>目标等权不等于实际每天等权：基础模型平均股票 / 国债 / 黄金市值占总资产约
{pct(base['mean_weights']['510300'])} / {pct(base['mean_weights']['511010'])} / {pct(base['mean_weights']['518880'])}，其余为现金或应收款。</p>
<p>本入口只接入公开派生账本。私人原始行情尚未接入，未在此重验市场来源；公司价值分析也不属于这个资产配置实验。</p></article>
<article id="history-result" class="layer"><h3>2 · 账本与评估层：赚了多少，花了多少？</h3>
<div class="metrics"><div><small>期末模拟总资产 · 元</small><strong>{money(base['final_nav'])}</strong><p>本金加累计损益，包含仍持仓资产的估值，未全部变现。</p></div>
<div><small>累计模拟盈利 · 元</small><strong>{money(profit)}</strong><p>期末资产减起始本金；已扣交易费用和滑点。</p></div>
<div><small>年化收益 · 基础成本</small><strong>{pct(base['cagr'])}</strong><p>把整个区间折算成年复合增速，不代表每年都赚这么多。</p></div></div>
<p>手续费共 {money(base['fees'])} 元；滑点共 {money(base['slippage'])} 元。
滑点指模型中成交价格相对参考价格的不利偏差。两项已反映在总资产里，不应再扣一次。</p>
<p>把交易成本提高后重新执行，期末资产为 {money(double['final_nav'])} 元，年化 {pct(double['cagr'])}。
双倍情景会改变交易路径，不能简单用基础收益减去一笔费用替代。</p>
<details><summary>固定研究费算进去，还值得吗？</summary>
<p>假设全部研究费由此项目承担，每月 100 美元，汇率固定为下列情景（非当前汇率）。
费用未从账户逐日扣款；下表是期末盈利再减区间费用，不是复投年化收益。</p>
<div class="scroll"><table><caption>基础成本账户 · 单独的经济费用情景（元）</caption><thead><tr><th>假设汇率</th><th>区间研究费</th><th>盈利减研究费</th></tr></thead><tbody>{expenses}</tbody></table></div></details></article>
<article id="history-benchmark" class="layer"><h3>3 · 基准层：比什么更好？</h3>
<p>同一窗口、相同起始本金，保留全部四类账户和两种成本。股票＋现金用于对照股票目标权重，
<strong>不是同风险对照</strong>；结果差异不能直接叫独立投资能力。</p>
<div class="scroll"><table><caption>成本后结果 · 不含固定研究费</caption><thead><tr><th>账户 / 成本</th><th>期末资产（元）</th><th>年化收益</th><th>最大回撤</th></tr></thead><tbody>{rows}</tbody></table></div></article>
<article id="history-risk" class="layer"><h3>4 · 风险与模拟执行层：哪里可能失真？</h3>
<p><strong>最大回撤 {pct(base['mdd'])}</strong>：模拟总资产从此前最高点到随后低点的最大跌幅，
不是最大单笔亏损，也不是未来损失上限。</p>
<p>黄金贡献基础盈利的约 {concentration}。这是事后会计归因，提示收益集中，不能推断以后继续有效。</p>
<p>基础账户有 {base['no_fill']} 笔模型未成交、{base['no_order']} 次未形成订单（例如整数份额或预算约束），两者不同。
下列卖单触及模型价格边界，被保留为未成交，没有补卖。这不等于交易所已确认当时无法卖出。</p>
<div class="scroll"><table><caption>基础账户的模型未成交记录</caption><thead><tr><th>执行日期</th><th>ETF代码</th><th>计划操作</th><th>结果</th></tr></thead><tbody>{failures}</tbody></table></div>
<p>其他模型成交采用开盘代理价及足量成交假设。官方逐日限价、停复牌和竞价排队 / 容量证据仍不完整。</p>
<p>完整买入后再全部清仓的样本为 {base['complete_round_trips']}，所以胜率<strong>未定义</strong>，不是 0% 胜率。部分卖出不能冒充完整交易。</p></article>
<article id="history-evidence" class="layer"><h3>5 · 证据层：这些数字可信到什么程度？</h3>
<ul><li>已核对：固定公开清单的文件哈希、8 条账户路径共 9,120 行资产加总恒等式。</li>
<li>尚未完成：本入口原始行情重验、真实可成交认证、独立未见样本或前瞻验证。</li>
<li>下一步：补执行证据，检验收益集中风险，按登记验证新的独立窗口；不能由此自动晋级。</li></ul>
<details><summary>查看逐项来源与版本，供复核使用</summary><ul>{sources}</ul>
<p>来源固定在公开提交 {r['source_commit']}。本机归档与固定清单一致；不是实时研究更新。</p>
<pre>清单 SHA-256：{r['manifest_sha256']}\n归档结论：{esc(r['decision'])}</pre></details>
<p><a href="/experiment-export?id=ca1">导出本页核对结果与来源（JSON）</a> · <a href="/#experiments">返回选择实验</a></p>
</article></section>'''
