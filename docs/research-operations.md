> 2026-10-25 更新：DQ001 的精确 20 格已完成独立来源裁决；当前行为以 [裁决与执行边界](dq001-reviewed-source-precedence.md) 为准。以下是 2026-10-24 修复记录，不据此宣称仍未裁决或已取得研究输入。

# 研究操作闭环与本轮修复（2026-10-24）

本轮对应 Issue #14 和 #15。只修复验证/运行/状态交付，不改策略、候选预算、行情、费用、数据争议或旧收益。主分支基线为 `92718c2ada35658d7e9ef512870f978e531a21f7`。

## 1. CA1 验证器 v2：明确检查，不依赖 assert

`research/ca1_20261022/verify_public.py` 改为显式抛出错误，普通、`-O`、`-OO` 和 `PYTHONOPTIMIZE=1/2` 下均执行完整公开哈希及净值检查。

原始 v1 校验器存为不可直接运行的 `verification_archive/v1/verify_public.py.txt`，原始公开清单也保存在该目录。**当前 PUBLIC_MANIFEST.json 仅更新校验器自身哈希**；其他证据、经济实现、发布证书及结果文件完全不变。v2 固定原始清单哈希，拒绝删除条目或修改其他历史绑定。原 PUBLICATION_AUDIT 仍仅描述原发布，不冒充 v2 的新审计。

回归覆盖有效证据、错误哈希/净值/行数/结论、删除清单条目；30 组子进程情景全部在临时副本运行。另有语义检查防止重复日期、非有限数字、意外原始价格字段及错误资产集合。

**存档经济引擎仍含 assert，未重写其源码或发布绑定。** 新统一历史执行入口拒绝优化模式；完整引擎硬化应另发版本。禁止直接以 `python -O implementation/run_batch.py` 运行旧引擎。公开验证是已有派生账本复核，不是从行情重跑，也不证明实盘可成交。

## 2. 一个入口、不同状态

```sh
python3 -m research.cli status
python3 -m research.cli preflight --experiment h002
python3 -m research.cli preflight --experiment h003
python3 -m research.cli preflight --experiment ca1
```

`status` 本身返回 `STATUS_REPORT_ONLY`；内部每条线分别展示实现与预检结果。T04 已按实际 H003 实现登记，但仍为未验证、DQ001 阻断。

| 状态 | 含义 |
|---|---|
| BLOCKED_DATA | 已知数据争议未处置；不读取行情、不联网、不运行策略 |
| BLOCKED_INPUTS | 缺少、错误或不匹配的输入；CA1 一次列出所有材料 |
| BLOCKED_RUNTIME / BLOCKED_CONFIG | 不支持的运行方式或冻结配置变化 |
| READY_FOR_ACQUISITION | 可以尝试抓取，尚未证明数据可用 |
| READY_FOR_CONDITIONAL_RESEARCH | 输入结构通过预检；不是供应商/公司行动完整认证 |
| READY_FOR_ARCHIVE_REPLAY | 原存档输入与证据按固定哈希齐全；不是新样本资格 |
| COMPLETED_CONDITIONAL_RESEARCH | 原候选驱动实际完成；仍为已查看研发样本 |
| COMPLETED_ARCHIVE_REPLAY | 原封存历史重跑完成，不是新独立市场证据 |
| FAILED | 配置/运行出错，不能当作研究完成 |

退出码：0 为收集完成/就绪/执行完成，**必须同时看 JSON status**；2 为阻断；1 为失败。`--report` 以独占方式写入新文件，拒绝覆盖旧结果。任何状态均不批准自动晋级或实盘。

有依据地处置数据争议后，原冻结候选才可由以下入口执行。现在执行会得到 BLOCKED_DATA，不会反复请求数据：

```sh
python3 -m research.cli run --experiment h002 --fetch \
  --data-dir /tmp/leek-input-new --output /tmp/leek-h002-new \
  --report /tmp/leek-h002-attempt-new.json
# 对已有同一快照运行H003；必须使用新输出目录：
python3 -m research.cli run --experiment h003 \
  --data-dir /tmp/leek-input-new --output /tmp/leek-h003-new
```

单源降级仍须显式 `--allow-single-source`，只用于网络不可用，不放宽已知报价冲突。未提供原始资料时不会生成数据、审批、回测成绩。

## 3. CA1 私有原始材料恢复

`preflight --experiment ca1` 对照固定 IMPLEMENTATION_MANIFEST、RUN_RELEASE 及其 evidence，分别列出 missing/mismatched。本轮公开仓库缺5项实现/输入文件及5项独立审计材料，不能仅补一个空文件就通过。

确有合法保存的**完整原始 capsule 目录**时，可在本地调用：

```sh
python3 -m research.cli preflight --experiment ca1 --private-root /path/to/lawful-original-capsule
python3 -m research.cli restore-ca1 --source /path/to/lawful-original-capsule \
  --destination /tmp/leek-ca1-private-new
python3 -m research.cli run --experiment ca1 --private-root /tmp/leek-ca1-private-new \
  --output /tmp/leek-ca1-replay-new --report /tmp/leek-ca1-attempt-new.json
```

恢复工具只接受原固定哈希对应的材料，写入仓库外的新私有目录，拒绝现有目标、路径逃逸、目录内符号链接和复制期间哈希变化。不重新生成批准证书、不覆盖原始资料、不上传数据。代码的复制/拒绝逻辑经过合成契约测试；本轮**没有取得缺失原件，未声称完成真实 CA1 恢复或全量重跑**。缺少完整原件时应寻找原档案，或者另行登记新的合法数据版本，不能伪造旧版本。

## 4. 当前提交的 CI，而非旧分支重放

新增 `research-operations.yml` 在 main push、以main为目标的PR和手动触发时检出**事件对应提交**，不使用固定旧PR清单。普通CI只收集无网络状态；手动可选择 preflight/run 和候选。手动尝试被阻断时退出非零，上传的状态JSON明确保留原因。

仅发布脱敏 readiness/attempt JSON；不发布原始行情、私有原件、底层驱动完整日志。完整研究账本保留在运行器输出目录；本工作流不是长期数据存储服务。需要独立归档派生结果时，应使用已审查的原始实验工作流或在本地保存。

旧 `real-history.yml`、`h002-research.yml` 去掉已删除开发分支的 push 触发，仅保留手动兼容。PR #13 是历史审查工具，仍未合入；不能用其绿灯替代当前提交校验。本轮未增设定时重复任务、未新增付费服务。

## 5. 验收边界

修复的是校验误通过、缺少一键预检/私有恢复入口、研究状态过期和CI绑定旧分支。DQ001没有解除，缺失原始材料没有恢复；H002/H003没有新增真实收益。本轮工程修复不算新的策略完成或成本后优势。

后续PR合并后需验证主分支CI，确认来源分支无新增提交/开放依赖后再清理。未合入本轮修复前，不声称main已包含这些改动。

来源：Python assert官方语义 https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement ；GitHub触发规则 https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow 。
