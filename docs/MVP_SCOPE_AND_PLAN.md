# Ecommerce Analytics Agent：MVP 范围与开发计划

## 1. MVP 要证明什么

这个 MVP 面向 Product Data Scientist 和 data-savvy Product Manager。用户可以询问正式定义的核心指标，也可以要求系统调查指标变化的原因。

MVP 需要证明两条端到端路径：

1. **Metric Q&A**：根据正式口径回答指标数值、趋势、比较和基础切片问题；
2. **Metric Investigation**：判断指标变化更可能来自真实业务、数据质量问题、疑似自动化／欺诈行为，还是证据不足。

所有回答都必须展示指标定义、时间范围、数据来源、质量状态和重要限制。系统不以“能够生成 SQL”作为成功标准，而以“结果可核查，并且不会在证据不足时伪造确定性”为标准。

## 2. 第一版支持范围

### 核心指标

- `visits`
- `visitor_purchase_conversion_rate`
- `visit_purchase_conversion_rate`
- `checkout_start_rate`（用于 checkout tracking availability 与受控 rate 查询）
- `gross_revenue`
- `net_revenue`

### 支持的问题类型

- 查询某一时间范围的指标值；
- 比较两个时间范围；
- 按已批准的维度切分；
- 识别指标变化开始的时间与主要 segment；
- 检查 bot、session inflation、fraud、tracking 和真实 campaign 等候选解释；
- 在数据不可用或证据冲突时拒绝下确定结论。

### 代表性验证场景

1. 正常指标查询；
2. Bot traffic；
3. Session inflation；
4. Tracking failure；
5. Fraud orders；
6. Real campaign negative control。

### 明确不做

- 任意数据库上的通用 Text-to-SQL；
- 自动修改指标定义或数据；
- 自动取消订单、封禁用户或发布实验；
- 完整 funnel、retention、LTV、forecasting 或 experiment suite；
- Multi-agent architecture；
- 生产级权限、监控和 SLA；
- 宣称生产可靠性、完整覆盖或已验证 ROI。

## 3. 标准回答结构

Metric Q&A 至少包含：

```text
Metric definition
Time range and filters
Result and comparison
Data quality status
Sources and limitations
```

Metric Investigation 至少包含：

```text
Classification
Affected segment
Evidence
Estimated metric impact
Confidence and limitations
Recommended action
```

## 4. 开发阶段与 Human Checkpoints

### Step 1：Semantic Layer

Agent 批量起草 table contracts、metric contracts、relationships 和 data-quality contracts。

**需要人工确认：Checkpoint 1**

- canonical visit 的 inactivity rule；
- identity stitching policy；
- conversion denominator；
- gross/net revenue 的组成与时间归属；
- confirmed fraud 和 suspected bot 的处理政策；
- 正式支持的 dimensions。

### Step 2：Raw Data Quality Baseline

Agent 自动 profiling 主键、空值、枚举、外键、join fanout、时间范围、延迟、重复和 schema drift。

**默认不需要人工确认。** 只有实际数据与业务定义冲突，或存在多个合理解释时才升级。

### Step 3：Trusted Data Layer

Agent 根据已批准 contract 实现 staging、canonical visits、trusted events、eligible orders、refund policy、metric health 和 audit evidence。

**需要人工确认：Checkpoint 2**

审核 reconciliation summary：哪些记录被调整或排除、指标影响、残余不确定性，以及正常业务变化是否被保留。

### Step 4：Governed Analytics Tools

Agent 实现受控的 metric lookup、health check、approved query、segment comparison 和 context retrieval。工具默认只读、参数化、限制来源，并隔离 `ground_truth/`。

**默认不需要人工确认。** 扩大数据权限、开放任意 SQL 或增加外部动作时必须确认。

### Step 5：Single-Agent Workflow

Agent 实现问题校验、指标解析、数据健康检查、调查计划、受控工具调用和证据化回答。

**需要人工确认：Checkpoint 3**

由用户体验 3–5 个问题，审核回答是否像合格 DS、是否过度确定、是否越权以及哪些信息最有业务价值。

### Step 6：Evaluation Suite

Agent 建立 deterministic checks、scenario tests、golden outputs 和 regression suite。表达类问题才考虑使用经过校准的 LLM judge。

**需要人工确认：Checkpoint 4**

批准六个代表性 golden cases 的业务标准和合理回答边界。

### Step 7：Demo 与项目包装

Agent 完成可重复运行入口、demo questions、evidence trace、架构图、README、限制和 portfolio case study。

**需要人工确认：Checkpoint 5**

确认 demo 故事、对外公开范围、能力成熟度标签和求职叙事。

## 5. Trace 与存档规则

每个开发批次都必须写入 `docs/DEVELOPMENT_LOG.md`，记录目标、输入、证据、决策、文件变化、命令、测试结果、风险、待确认项和 commit。

Git commit 保存代码历史；development log 保存业务与技术决策历史；checkpoint review 保存人类确认历史。三者共同构成项目 trace。

不记录凭据、token、敏感个人信息或不可审计的内部思维过程。

## 6. 当前状态

- 合成 raw dataset、incident ground truth 和 expected reference 已存在；
- 业务场景说明已存在；
- 当前 deterministic agent 代码是 `EXPERIMENTAL`，只证明部分技术路径可运行；
- Semantic Layer 已在 Checkpoint 1 获得业务 Owner 确认；
- Step 2 Raw Data Quality Baseline 与 Step 3 Trusted Data Layer 已完成；
- Checkpoint 2 reconciliation 已获得业务 Owner 确认；
- Step 4 Governed Analytics Tools 已完成：只开放六个批准指标、批准维度和参数化只读查询，并强制执行 health status 与 Net Revenue as-of policy；
- Step 5 Single-Agent Workflow 已完成，Checkpoint 3 已由业务 Owner 批准；
- Step 6 Evaluation Suite pilot 已建立并通过 8/8 golden cases；Checkpoint 4 已由业务 Owner 批准；
- Step 7 Demo 与项目包装已完成，Checkpoint 5 已由业务 Owner 批准；
- Trusted layer 与 governed tools 均以已批准 contracts 为业务事实来源，并隔离 evaluator-only `ground_truth/`。

MVP 已完成。后续新增仓库连接、UI、监控、指标或自动化动作，应作为新的明确 scope 和 approval cycle 管理。

