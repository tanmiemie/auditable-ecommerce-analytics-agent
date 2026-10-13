# Ecommerce Metric Reliability：业务场景说明

## 这个项目解决什么问题

一家电商公司的 Visits、Conversion、Orders 或 Revenue 突然变化时，数字本身不能说明原因。变化可能来自真实业务，也可能来自自动化流量、欺诈订单、埋点故障或上游数据处理问题。

这个项目要开发的不是一个“替代 Data Scientist”的聊天机器人，而是一套可审计的调查工作流。它需要先确认指标定义和数据是否可信，再定位变化发生的时间与人群，使用独立数据源交叉验证，最后明确区分事实、推断和仍然未知的部分。

第一版围绕四类常见问题展开：

1. 自动化流量是否制造了虚假的访问增长；
2. Visits 暴涨是否来自 session 或 identity 规则变化；
3. Orders 增长是否包含欺诈或促销滥用；
4. Metric 下降是否来自 tracking failure，而不是真实业务恶化。

项目同时保留真实营销活动、促销增长、商品缺货和产品体验变化等正常业务场景。这样才能检验系统是否会把所有异常都误判为数据问题。

---

## 1. 自动化流量：访问增长不一定来自真实用户

### 明显的商品爬虫

商品爬虫可能在短时间内反复访问大量商品页，却几乎不加购或购买。常见信号包括：

- 单个设备或 IP 产生大量访问；
- 页面访问间隔高度规律；
- Session 很短，但浏览商品数异常高；
- 一天中长时间持续活动；
- User agent 带有自动化工具特征；
- Visits 和 page views 上涨，但 Orders 基本不变。

这些信号可以支持“疑似自动化流量”的判断，但仅凭分析数据不能证明对方一定是 bot。

### 伪装成正常用户的自动化行为

更复杂的自动化流量可能使用正常 user agent、轮换 IP 或设备，并模拟搜索、浏览甚至加购。它可能集中访问某些商品或品牌，目的包括价格监控、库存监控、账号攻击或优惠滥用。

这种情况不能只依赖访问次数判断，需要组合观察：

- 行为序列是否机械重复；
- 活动时间是否过于规律；
- Device、IP 或账号是否异常复用；
- 浏览是否集中在少量商品；
- 加购、结账和购买之间是否符合真实用户行为；
- 流量增长是否能被营销活动解释。

### Agent 应该怎样表达

不合格的结论：

> 这些访问都是 bots。

更合理的结论：

> 访问增长主要集中在具有自动化行为特征的流量中，疑似 bot traffic。分析结果支持进一步调查，但仍需结合 WAF、安全系统或其他独立来源确认。

系统需要区分“观察到异常模式”和“确认对方身份”。

---

## 2. Visits 暴涨：先确认计数规则有没有改变

访问量增加并不自动等于用户增长，也不能全部归因于 bot。以下几类问题可能产生相似的表面现象。

### SDK 重复发送事件

移动端 SDK 重试可能让同一次行为被记录两次。此时可能看到：

- Page views 或 events 增加；
- Unique users 基本不变；
- Events per user 或 events per session 突然上升；
- 重复集中在某个平台或 App version；
- 重复记录的时间戳几乎相同。

这种问题通常可以通过稳定的 event identifier 去重，但原始记录仍应保留以便审计。

### Sessionization 规则变化

系统可能原本在用户连续 30 分钟无活动后才创建新 session，后来错误地改成 5 分钟。用户行为没有改变，同一段访问却被拆成多个 sessions。

常见表现是：

- Sessions 或 raw visits 上升；
- Unique users 和 Orders 没有同步增长；
- 平均 session duration 下降；
- Events per session 下降；
- Session conversion rate 被动下降。

这类问题说明 SQL 即使完全正确，结果仍可能因为上游定义变化而失真。正式 Visits 指标需要使用统一的 canonical visit 规则，而不是直接计算 raw `session_id`。

### Cookie 或 Device ID 重置

如果新版本不断创建新的 anonymous ID，同一个人会被计算成多个访客。可能看到：

- Unique visitors 上升；
- New visitor share 上升；
- Returning visitor rate 下降；
- 登录用户数量没有同步增长；
- 同一个注册账号关联越来越多 anonymous IDs。

调查时需要检查 identity mapping、版本发布时间和匿名身份生成规则。

### Referral loop

支付、登录或广告跳转后返回网站时，系统可能错误创建新 visit。此时新增 sessions 往往集中在 checkout 或 login 后，用户数和订单数却没有对应增长。

### 真实 Marketing Campaign

营销活动也可能真的带来大量低转化流量。可信的业务增长通常可以观察到：

- Visits 集中在活动对应的 channel 和 campaign；
- Spend、click 和 landing-page sessions 同时变化；
- 用户数量与访问量基本匹配；
- 活动开始和结束时间与增长窗口一致。

这个场景是重要的反例。系统不能因为流量突然增加，就默认存在 bot 或 tracking issue。

---

## 3. Fraud Orders：订单增长不一定都是收入增长

### Payment velocity attack

攻击者可能先用大量小额订单测试支付方式，随后尝试更高金额的交易。常见信号包括：

- 同一设备或支付标识关联多个账户；
- 短时间出现大量小额测试订单；
- 多个账号共享 IP、设备或支付信息；
- 随后出现更高金额的尝试；
- 支付失败或退款比例异常。

### Promotion abuse

用户可能创建多个账户，重复使用新用户优惠、推荐奖励或免邮活动。可能看到：

- 多个账号共享设备或支付信息；
- 订单金额集中在刚好达到优惠门槛的位置；
- 新用户订单和 coupon 使用突然增加；
- Gross sales 上升，但 margin 下降。

### 延迟出现的 fraud label

订单在当天可能看起来完全正常，数周后才收到 chargeback 或风控结论。因此最近订单的 fraud label 天然不完整。

分析需要区分：

- 订单发生时间；
- 支付完成时间；
- 风控确认时间；
- Chargeback reported date；
- 当前分析使用的 as-of date。

### 真实促销增长

真实促销也会带来订单和新用户增长。它通常同时具有：

- Campaign 和 coupon 使用符合活动规则；
- Payment success 保持正常；
- Device 或支付信息没有异常复用；
- 后续退款或 chargeback 没有异常上升。

Agent 不能把“异常增长”直接等同于 fraud。

### Agent 的权限边界

第一版 Agent 可以：

- 识别异常 pattern；
- 定位受影响的时间和 segment；
- 估计指标影响；
- 展示 supporting evidence；
- 标记 suspected fraud；
- 建议 Fraud 或 Risk 团队审查。

第一版 Agent 不可以自动取消订单、封禁账户或把可疑行为宣布为已确认欺诈。

---

## 4. Tracking Issues：事件下降不一定代表用户行为下降

### 整个事件停止上报

例如 `begin_checkout` 从某天开始突然归零。调查需要检查：

- 是否所有平台都缺失；
- 数据 pipeline 是否仍有其他事件进入；
- Event 是否改名；
- Server-side orders 是否仍然发生；
- 问题是否与某次 release 同时开始。

### 只有一个平台或版本受影响

Web 和 Android 可能正常，只有某个 iOS 版本停止发送 checkout event。总体指标可能只下降一小部分，因此必须按 platform、app version、country 和 event date 切片。

### Event rename

埋点迁移可能把旧名称替换成新名称。如果只查旧事件，指标会突然归零；如果迁移期把新旧事件直接相加，又可能重复计算。

系统需要保留原始事件名，并使用有版本和时间边界的 canonical mapping。

### Property missing

事件数量可能完全正常，但 `product_id`、`cart_value`、`experiment_id` 或 `payment_method` 等关键字段消失。此时总体事件数仍可使用，但按商品、实验或支付方式的分析可能已经失效。

### Client-side 与 server-side 不一致

如果 client purchase event 下降，而 server-side completed orders 保持稳定，更可能是 tracking 问题，而不是真实购买下降。独立来源的交叉验证是判断数据问题的重要方法。

当缺失事实无法可靠重建时，系统应该把受影响指标标记为 unavailable，而不是根据订单反推不存在的 client events。

---

## 5. Agent 应采用固定的调查流程

当用户问“昨天 Visits 增长了 45%，发生了什么”时，Agent 不应该立即自由解释。第一版调查流程应包括：

1. 确认指标定义、时间范围和比较基准；
2. 检查数据新鲜度、完整性和最近的 schema 变化；
3. 对比 users、sessions、events 和 orders 是否同步变化；
4. 确认变化开始和结束的时间；
5. 按 platform、app version、channel 和 country 切片；
6. 检查重复率、identity 变化以及 user/session/event 比例；
7. 对照 campaign、release 和已知 incident timeline；
8. 使用独立来源交叉验证；
9. 输出证据、可能原因、指标影响和仍然存在的不确定性。

建议的输出结构是：

```text
Classification
当前最合理的分类，但不能超过证据边界。

Affected segment
受影响的平台、版本、渠道、国家或其他切片。

Evidence
支持当前判断的可核查事实。

Estimated metric impact
异常对正式指标造成的影响。

Confidence
置信度以及仍然缺少的证据。

Recommended action
在 Agent 权限范围内可以采取的下一步。
```

---

## 6. 如何评价 Agent 是否做对

评价不能只看最终有没有猜中一个标签。还需要判断：

1. 是否发现了真实异常；
2. 是否定位正确的时间和 segment；
3. 是否区分真实业务变化与数据问题；
4. 是否使用合适的独立数据源交叉验证；
5. 是否量化指标影响；
6. 是否把相关性夸大成因果；
7. 是否在证据不足时保留不确定性；
8. 是否提出了符合权限边界的行动建议。

系统最终应区分四种结果：

- 数据或 tracking 问题；
- 疑似自动化或欺诈活动；
- 真实业务变化；
- 证据不足，无法可靠分类。

准确日期、隐藏根因、受影响版本以及标准答案属于 evaluator-only 信息，保存在 `ground_truth/` 中，不应提供给被测试的 Agent。

