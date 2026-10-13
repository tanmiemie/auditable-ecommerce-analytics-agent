# Semantic Layer 草案

## 这份定义解决什么问题

同一段原始数据可以产生多个“技术上正确”但业务含义不同的答案。Semantic Layer 的作用，是在人或 Agent 查询数据前，先明确每张表代表什么、每一行是什么、怎样连接，以及正式指标允许使用哪些规则。

本草案只定义，不执行 cleanup。机器可读版本位于：

- `config/semantic_layer.yml`
- `config/metrics.yml`
- `config/data_quality_contracts.yml`

三个文件已经在 Checkpoint 1 获得业务 Owner 批准，状态为 `approved_checkpoint_1`。

## 核心表

| 表 | 每行代表什么 | 主键或候选键 | 在 MVP 中的作用 |
|---|---|---|---|
| `users` | 一个注册账户 | `user_id` | 国家、初始平台、员工标记 |
| `identity_map` | 一条匿名身份到注册用户的连接 | `anonymous_id` | 登录前后身份拼接 |
| `sessions` | 来源系统生成的一个 raw session | `session_id` | 原始访问与平台上下文 |
| `events` | 一个发送到采集系统的客户端事件 | `event_id` 候选键 | 行为时间、事件名称与重复检测 |
| `orders` | 一个 server-side order | `order_id` | Revenue 与 conversion numerator |
| `refunds` | 一次 refund request | `refund_id` | Net revenue adjustment |
| `campaigns` | 一个营销活动 | `campaign_id` | 真实业务变化的解释上下文 |
| `app_releases` | 某平台上的一个版本发布 | `platform + app_version` | Tracking 或行为变化的时间上下文 |

## 已核验的数据事实

- `users` 10,000 行，`user_id` 唯一且无缺失；
- `identity_map` 10,000 行，其中9,743条 matched、257条 pending；
- `sessions` 71,279 行，`session_id` 唯一；822行使用 `v2_5min`；
- `events` 320,986 行，存在896条重复 `event_id`；
- `orders` 5,593 行，`order_id` 唯一；85笔标记 confirmed fraud；4笔属于 employee accounts；两者没有重叠；45笔没有 session；
- `refunds` 185 行，全部能关联订单；
- 当前185笔退款全部在对应订单后的30天内发起；
- 已检查的 users、sessions、orders、refunds、campaigns 外键没有 orphan；
- 所有订单金额满足 `subtotal - discount + shipping_fee + tax = order_total`；
- Refund completion 与 ingestion 可能发生在订单观察期之后。

## 重要概念边界

### Raw session 不等于 Visit

`sessions` 的一行代表来源系统创建的 session。正式 Visits 指标应在统一 inactivity rule 下生成 canonical visit，不能直接 `COUNT(session_id)`。

### Anonymous identity 不等于确认用户

只有得到批准的 identity mapping 才能把匿名行为归到注册用户。Pending 或 ambiguous mapping 不能被静默强制拼接。

### Suspected bot 不等于 confirmed bot

行为信号可以支持调查和指标质量处理，但 Agent 不得把可疑流量表述成已确认攻击。

### Client event 不等于 server transaction

Events 用来理解客户端行为；Orders 是 server-side commercial fact。两者不一致时，应调查 tracking，而不是用订单伪造缺失事件。

### Campaign 和 Release 是上下文，不是因果证明

时间重合可以提高某个解释的可信度，但仍需结合 segment、行为变化和独立来源。

## Checkpoint 1：已由业务 Owner 确认

下面的问题会改变正式指标结果，因此在 cleanup 前必须确认：

1. **已确认：** Canonical Visit 采用30分钟无活动规则。同一 canonical visitor 的有效事件按 `event_ts` 排序，相邻事件间隔超过30分钟才开始新的 visit；raw session 与 sessionization version 保留用于审计。
2. **已确认：采用平台差异化 Identity Stitching。** 只有 `matched` 且无冲突的 identity 可以拼接。App（iOS/Android）允许把同一 `anonymous_id` 的已有历史行为 retroactively 归到 `user_id`；Web 因浏览器可能多人共用，只拼接 `effective_from` 及之后的行为。`pending`、`ambiguous`，以及出现一对多用户、账号切换或设备重新归属迹象的 identity 均不拼接，进入 review；所有 raw identity 字段保留用于审计。
3. **已确认：同时保留两个正式指标。** Visitor Purchase Conversion 使用 unique canonical visitors；Visit Purchase Conversion 使用 canonical visits。
4. **已确认：** Visitor-level 使用同一统计时间范围，不增加7天或30天窗口；Visit-level 订单必须通过 `session_id` 归属 canonical visit，不使用时间窗口补充归属。无 `session_id` 的订单不进入 Visit Conversion，但在身份可靠时仍可进入 Visitor Conversion 和 Revenue。
5. **已确认：** Gross Revenue 使用 eligible paid orders 的 `order_total`，即 `subtotal - discount + shipping_fee + tax`；它包含运费和税、扣除折扣，并且在 completed refunds 扣减前计算。
6. **已确认：采用30天成熟期的订单 cohort Net Revenue。** Refund 在 `requested_at` 时即从对应订单收入中扣除，不等待 `completed_at`。只有当 `report_as_of_ts >= order_ts + 30 days` 时，订单的 `refund_window_complete` 才为 true，并进入正式 Net Revenue；尚未完成退款周期的收入单独披露为未成熟收入。超过30天才发起的退款属于政策例外，进入 review，不静默处理。
7. **已确认：** `is_confirmed_fraud = 1` 的订单从 Revenue 和 Conversion numerator 中排除。Employee orders 不排除，继续进入 Revenue 与 Conversion，并通过关联 `users.is_employee` 派生 `is_employee_order` flag，支持筛选和贡献披露；员工 visitor/visit 仍保留在 Conversion denominator，除非命中其他已批准的排除规则。
8. **已确认：采用 raw + bot-filtered 双口径。** Visits 和 Conversion 等 traffic-derived headline metrics 默认使用 bot-filtered 值，同时必须展示 raw 值、排除量和排除比例。行为规则识别的流量只能称为 `suspected_bot`，除非有独立来源确认，否则不得描述为 confirmed bot；raw records、`bot_reason` 与 `bot_rule_version` 必须保留以便审计。Revenue 不因 suspected-bot traffic 自动排除订单，仍以 confirmed-fraud policy 为准。
9. **已确认：** 通用维度为 `date`、`platform`、`channel` 和 `country`；App/visit 分析增加 `app_version`，campaign investigation 增加 `campaign_id`，order/revenue 分析增加 `is_employee_order`。Traffic 与 Conversion 的 country 使用 `users.country`，Revenue 的 country 使用 `orders.shipping_country`。

Conversion denominator 与 MVP attribution policy 已由业务 Owner 确认；两个指标必须使用不同名称展示，不允许用未限定的 `purchase_conversion_rate` 静默代表其中一个。

Checkpoint 1 已全部确认。Semantic Layer 状态已改为 `approved_checkpoint_1`，项目于2026-10-13进入 data cleanup。

