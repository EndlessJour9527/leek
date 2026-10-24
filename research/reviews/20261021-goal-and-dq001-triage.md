# 2026-10-21：研究目标确认与 DQ001 旧账本影响定位

## 目标和当前决策

持续吸收开源策略与工程经验，用真实历史和前向证据调试模型，直到达到预登记的阶段标准；不以不断调参得到一条好看的历史曲线作为成功。沿用 docs/research-charter.md 及 research/trader_team.json，不另起重复团队、重复调度或降低晋级门槛。

当前没有值得批准进入部署评审的模型。MA120/H001 保留负面历史结果；H002 已实现但 DQ001 未解决，不能声称它已产生真实收益。不同研究席位可同时推进文献、独立实现与工程测试，受影响数据的有效回测与晋级仍阻断。已有10个研究席位是分工注册，不等于10个已部署的并行交易Agent。

## 本次实际执行：独立检查已下载的旧结果

没有重新计算策略收益，没有修改行情，没有解除数据冲突。

输入为 PR5 的原始派生结果 ZIP（2026-10-20，Actions run 39446205344，artifact 12276081553）。本次在会话计算环境确认文件 SHA-256 为：

`49c78bbddd7cc66e57f65b278b073e7f1f2e0b2267b16978cd27406774403b71`

争议字段依据固定提交 7682219e09580d842ac36152e674d146e93f0e86 下的 research/results/DQ001_source_audit.json，Git blob 为 7c63a9d4a5de690d158c35b64778d3c7c738db92。该清单表明2020-08-21、24、25、26、27五日，东方财富与腾讯的开高低收共20格相差0.001元。

对8份派生账户报告逐一复核的新增事实：

| 报告组 | 五个争议日内订单尝试数 | 各争议日持仓 | 旧报告隐含收盘价 | 相同持仓下的单日估值差 |
| --- | ---: | ---: | --- | ---: |
| 基准/压力费用的买入持有 | 均为0 | 均为2400份 | 市值/份额与清单腾讯收盘一致 | 2.400元 |
| 基准/压力费用的MA120 | 均为0 | 均为2400份 | 市值/份额与清单腾讯收盘一致 | 2.400元 |
| 基准/压力费用的H001 | 均为0 | 均为2400份 | 市值/份额与清单腾讯收盘一致 | 2.400元 |
| 基准/压力费用的现金基准 | 均为0 | 0 | 无持仓，不反推价格 | 0.000元 |

只是在固定原有持仓下计算 2400 × 0.001 = 2.4 元。**不能把五天的估值差简单累加成交易亏损，不能据此宣称完整回测收益或最大回撤不变。** 此处没有重建原始OHLC，也没有重新计算TR、MA120或H002。争议价格仍可能影响后续指标、状态及成交。旧报告中无当日成交不等于差异无经济意义。

旧报告的估值与争议清单中腾讯一侧一致，也不证明腾讯正确。第三方供应商数据可能共享上游；需要额外的独立证据或原始交易所记录。已尝试通过当前网页读取工具查询Yahoo历史行情，未取得可读响应，因此第三来源核验仍为未完成，DQ001保持UNRESOLVED。

## 可复现的旧报表检查

下列代码只读取已下载的派生ZIP和仓库差异清单，无网络、无行情修补、无收益重跑。ZIP不重新提交到公开仓库。

```python
import hashlib
import json
import zipfile
from decimal import Decimal as D
from pathlib import Path

archive = Path('leek-real-history-results-20261020.zip')
expected = '49c78bbddd7cc66e57f65b278b073e7f1f2e0b2267b16978cd27406774403b71'
if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
    raise ValueError('Archived result checksum mismatch')
audit = json.loads(Path('research/results/DQ001_source_audit.json').read_text())
closes = {r['date']: r for r in audit['mismatches'] if r['field'] == 'close'}
with zipfile.ZipFile(archive) as z:
    for name in sorted(n for n in z.namelist() if n.endswith('.json') and n != 'summary.json'):
        report = json.loads(z.read(name))
        rows = [r for r in report['daily'] if r['date'] in closes]
        if len(rows) != len(closes):
            raise ValueError('Missing or duplicated disputed-date rows')
        orders = [o for o in report['orders'] if o['execute_on'] in closes]
        for row in rows:
            ref = closes[row['date']]
            qty = D(row['quantity'])
            implied = D(row['market_value']) / qty if qty else None
            if implied is not None and implied != D(ref['tencent']):
                raise ValueError('Old report no longer matches audited Tencent close')
            delta = qty * (D(ref['eastmoney']) - D(ref['tencent']))
            print(name, row['date'], 'order_attempts_in_window=', len(orders),
                  'qty=', qty, 'same_position_one_day_mark_delta=', delta)
```

## 本次复核的开源经验及具体用途

- vn.py TurtleSignalStrategy 固定源码的20日入场/10日退出窗口和订单回调分离已核对。Leek H002只借鉴通道思想，不复制包含做空、ATR停止单及分批加仓的完整海龟策略。源码：https://github.com/vnpy/vnpy_ctastrategy/blob/c212d603e68a5f4dbbc160fe8f7f8b1e06be2494/vnpy_ctastrategy/strategies/turtle_signal_strategy.py
- Qlib工作流和Task Management：学习可追溯实验记录、按时间拆分和滚动任务，不把框架自带示例成绩当成本项目结果。https://qlib.readthedocs.io/en/latest/component/workflow.html 与 https://qlib.readthedocs.io/en/latest/advanced/task_management.html
- Backtrader订单执行文档：区分信号时点、下一bar执行及订单类型；下一开盘代理不等于可成交证明。https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/
- Freqtrade前视/递归分析：学习截断与全数据计算对照、不同预热长度对照。用于测试思想，不复制交易引擎，也不把加密货币策略直接当作A股策略。检查不到未触发信号，必须记录测试覆盖面。https://www.freqtrade.io/en/stable/lookahead-analysis/ 与 https://www.freqtrade.io/en/stable/recursive-analysis/

没有新增第三方运行依赖或复制第三方实现；本次没有新增候选，不消耗全队8个候选的阶段预算。

## 下一轮的明确验收任务

1. 数据席位：针对五个争议日逐字段获取独立来源、说明原价/调整价和精度，并存原始响应指纹。证据不能只写“多数来源相同”。不得通过放宽容忍度解除DQ001。
2. 验证席位：仅在数据处理决议获独立核对并登记后，冻结新快照；重跑现金/买持/MA120/H001/H002及两种费用，保留与旧结果的差异和拒单。旧2020—2025样本仍为研发样本。
3. 策略席位：每席每轮最多一个预登记候选，记录来源、适用市场、移植差异和失败原因；不能事后选择最佳参数并占用同一个封存集。
4. 达到M2/M3后才报告“阶段满意”：未见样本、多种不同市场暴露、风险可比基准、压力成本，以及冻结后的真实前向日志。样本数门槛只是最低信息量，不构成统计显著性或盈利保证；低频策略缺少交易时应延长观察，不为了凑样本强制交易。

本次状态：**新的旧报表影响定位已完成；没有新的有效策略回测结果；不修改main、不合并PR、不连接券商。**
