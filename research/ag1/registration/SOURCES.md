# 研究依据与来源边界（2026-10-18查阅）

1. Jegadeesh & Titman (1993), Returns to Buying Winners and Selling Losers, Journal of Finance 48(1), 65–91。读原文§I及摘要：中期相对强弱、排序与月度组合的原始研究依据；原文是美股多空、不同形成/持有期及跳一周设置，并不是本批中国ETF/12-1长仓规则的原样复制。
   - 原文大学镜像：https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
   - 出版商：https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x
2. Kenneth R. French Data Library, Detail for Monthly Momentum Factor。官方构造说明以prior (2–12)月收益排序和月度形成组合，支持“跳过最近月”的可复核端点习惯；本批只借用信号时序，不借用其美股收益结论。
   - https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html
3. Asness, Moskowitz & Pedersen (2013), Value and Momentum Everywhere。作者机构原始研究摘要说明动量证据跨市场同时有共同风险。只作为研究动机；作者摘要/网页PDF不是本批成功证明，未拿其数值当目标。
   - https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere
4. 中证500官方指数编制方案（2022-05版本）。§三说明排除沪深300及规模前300，再以流动性/规模选500；支持规模层次设计，不能冒充2020历史成份快照。
   - https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000905_Index_Methodology_cn.pdf
5. 沪深300官方编制方案：大盘锚点的指数身份，历史版本仍需数据清单留存。
   - https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf
6. 南方512100官方产品页/资料概要：产品成立2016-09-29、跟踪中证1000；官方说明中证1000在中证800之外形成较小规模补充。产品页会混有当前收益展示，本次未以那些数字筛选或改参数。
   - https://www.nffund.com/new/personal-financing/detail.html?fundCode=512100
   - https://www.nffund.com/main/files/2023/12/18/927662281222.pdf
7. 易方达159915官方产品资料和深交所公告：成立2011-09-20、创业板指数暴露及上市信息。
   - https://static.efunds.com.cn/html/fund/159915_fundinfo.htm
   - https://www.szse.cn/disclosure/notice/fund/t20111207_516231.html
8. 南方510500官方产品入口（动态页面空字段不算完成验证）：具体上市/产品证据已由数据预检保存，见相邻data_preflight来源manifest。
   - https://www.nffund.com/new/personal-financing/detail.html?fundCode=510500

产品成立/上市、512100合并与159915停牌的实际证据文件、官方或公告镜像URL、抓取时间、SHA256详见../data_preflight/source_manifest_preflight.json、source_manifest_events.json；不能把当前介绍页升级为全历史无公司行动证据。文献只提供经济假设及预注册参数的外部理由，不证明四ETF策略盈利。G2阈值和本批账户规模是研究设计者预设的审查标准，不声称来自原论文或用户实盘偏好。
