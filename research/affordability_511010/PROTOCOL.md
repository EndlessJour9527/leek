# 511010 fixed-initial-budget overlap diagnostic — 2026-11-01
Before aggregation: target ML0022019–2025; only retained M1 overlapping 2021-10-18..2025-12-31 observations. Exclude2026 and do not infer2019–2021-10-17. Read pinned original Tencent raw `day` (O,C,H,L) and Sohu hq(O,C,...,L,H), exact Decimal OHLC/date equality and retained calendar agreement. Fail closed on missing/conflicting/duplicate/invalid rows or identity/hash mismatch. No adjusted field fallback, price imputation, dividend assumption or account-derived prices.

Fixed reference capital50000, fraction0.20,100-unit lot, budget10000. ML002 itself specifies BEFORE costs only. Supplemental cash needs apply the existing frozen real_history_protocol base/stress research costs: BUY raw open*(1+slippage_bps/10000), round UP to0.001 tick; commission=max(minimum,100*execution_price*rate) rounded HALF_UP to cents. Base2bps/min5/slip5bps; stress4bps/min10/slip10bps. This is an explicitly labeled reuse of reference research costs, not a broker tariff or CA1 1/3 allocation. Minimum one-lot cash is100*slipped_price+commission. Report all observations, affordable count for principal/base/stress, min/max and all tied dates.

Fixed initial budget counterfactual only; no changing NAV/cash/entry signal/previous close sizing, no return or dynamic trading path. Units: retained exchange rules fund quotation RMB per share and100-unit secondary lot. Raw-day field and cross-source equality support conditional nominal-price interpretation, not independent provider adjustment/history publication certification. Daily open is not guaranteed executable. Existing ML002 SSE/Tencent full-panel contract remains blocked; Sohu/Tencent M1 is a separately identified source pairing, never a substitute gate. No new model/candidate/budget/fee/universe. Preserve previous price-access failure and all limitations. Local protocol record has no independent trusted timestamp.


## 独立准备审查边界补充（2026-11-01）
独立准备审查确认M1与ML002目标窗口的交集为2021-10-18—2025-12-31，共1024个交易日；两源唯一日期集合及逐日OHLC一致，相关原件哈希匹配。这是该重叠原件的有界核验，不外推未覆盖区间。

**PR22原指标只比较原始open×100与10000元，成本前。** base佣金0.02%/最低5元/滑点5bp、stress佣金0.04%/最低10元/滑点10bp，以及买价向上取0.001元tick，仅为单列的既有研究配置附加情景，不修改原指标，不是券商实际费率。

腾讯day字段与既有M1审计支持有界名义原始价解释，不能等同完整unadjusted或point-in-time合同。搜狐×腾讯的M1重叠核验不能替代ML002要求的SSE官方×腾讯源门，trainable=false及原BLOCKED_PRICE_PANEL保持。独立准备审查也不等于公开发布放行或经济有效性证明。
