# 授权积分钱包设计

## 背景

当前商业后台已经有客户、授权码、设备绑定、心跳、停用、恢复正式版和体验用量秒数。新的商业规则要把“体验用量”升级为“积分钱包”，让试用版、月付版、年会员都走同一套服务端积分扣费逻辑。

目标是让客户买到的不是无限云端额度，而是明确的可消费积分。客户端每次调用飞影、阿里云等会产生费用的云端能力前，必须先向服务器申请扣积分。服务器积分不足时直接拒绝，客户端不能只靠本地判断。

## 已确认规则

- 飞影成本参考价：10 积分 / 秒。
- 客户扣费价：15 积分 / 秒。
- 试用版：开通赠送 1300 积分。
- 月付版：开通赠送 48000 积分。
- 年会员：每月发放 48000 积分。
- 年会员积分不结转，下个月刷新为 48000，而不是叠加上月余额。
- 积分不足时不能发起云端生成。
- 生成失败时退回本次预扣积分。

## 套餐与积分

套餐字段继续使用现有 `plan`：

- `trial`：试用版，默认 1300 积分。
- `monthly`：月付版，默认 48000 积分。
- `yearly`：年会员，每月 48000 积分，不结转。
- `lifetime` / `custom`：保留入口，第一版按后台手动配置积分处理。

后台创建授权时，“体验用量（秒）”改为“赠送积分”。当选择套餐时，表单自动填入默认赠送积分：

- 试用版：1300
- 月付版：48000
- 年会员：48000

正式套餐不再默认不限量，除非后台明确把该授权配置为不限积分。

## 数据模型

在授权记录上新增或替换以下字段：

- `credit_balance`：当前剩余积分。
- `credit_granted_total`：累计发放积分。
- `credit_used_total`：累计实际消耗积分。
- `credit_plan_allowance`：当前套餐周期发放额度。
- `credit_unit_price_hifly_per_second`：飞影扣费单价，默认 15。
- `credit_period_started_at`：当前积分周期开始时间。
- `credit_period_ends_at`：当前积分周期结束时间。
- `credit_last_refreshed_at`：上次周期刷新时间。
- `credit_unlimited`：是否不限积分，默认 false。

保留旧的 `usage_limit_seconds` 和 `usage_used_seconds` 只做兼容迁移，不再作为新 UI 的主要概念。

新增积分流水记录，建议存储在同一商业中心数据结构中：

- `credit_txn_id`
- `license_id`
- `customer_id`
- `activation_id`
- `type`：grant / reserve / consume / refund / adjust / monthly_refresh
- `amount`
- `balance_after`
- `feature`
- `seconds`
- `provider`
- `task_id`
- `status`
- `note`
- `created_at`

## 扣费流程

客户端发起云端任务前调用服务端扣费接口。

1. 客户端根据脚本文本或任务时长估算生成秒数。
2. 服务端按 `秒数 * 15` 计算本次应扣积分。
3. 如果授权已停用、过期、设备不匹配或积分不足，服务端拒绝。
4. 如果积分足够，服务端创建 `reserve` 流水并预扣积分。
5. 客户端开始调用飞影或阿里云。
6. 生成成功后，服务端把该流水确认成 `consume`。
7. 生成失败后，服务端创建 `refund` 流水并退回预扣积分。

第一版可以复用当前 `claim_usage` 思路，把“秒数”升级成“积分预扣”。后续再拆成更精细的 reserve / commit / refund 三个接口。

## 接口设计

保留现有激活、心跳和授权接口。

新增或升级：

- `POST /license/credits/reserve`
  - 请求：activation_token、machine_code、provider、feature、seconds、task_id、context。
  - 响应：reserved、cost_credits、balance_after、reservation_id。

- `POST /license/credits/commit`
  - 请求：reservation_id、task_id、actual_seconds。
  - 响应：consumed、final_cost_credits、balance_after。

- `POST /license/credits/refund`
  - 请求：reservation_id、task_id、reason。
  - 响应：refunded、refund_credits、balance_after。

- `POST /admin/api/licenses/{license_id}/credits/adjust`
  - 后台手动加积分或扣积分。

- `POST /admin/api/licenses/{license_id}/credits/refresh-period`
  - 手动刷新年会员当月积分，自动任务也走同一逻辑。

## 后台界面

授权表从“体验用量”调整为“积分”：

- 套餐
- 剩余积分
- 本月已用
- 累计已用
- 周期结束时间
- 状态
- 操作：加积分、扣积分、刷新本月积分、停用、重置设备、恢复正式版、查看明细

创建授权表单：

- 套餐
- 可绑定设备数
- 赠送积分
- 到期时间
- 功能权限
- 授权备注

选择试用版、月付版、年会员时自动填入默认赠送积分，但后台可以手动修改。

## 客户端提示

客户侧不显示复杂账本，只显示简单文案：

- 剩余积分：xxxx。
- 本次预计消耗：xxxx 积分。
- 积分不足，请续费或联系管理员充值。
- 生成失败，已退回本次预扣积分。

云端生成按钮必须在服务端预扣成功后才继续调用供应商 API。

## 年会员周期刷新

年会员每月刷新为 48000 积分，不结转。

刷新规则：

- 周期到期后，下一次心跳或扣费时触发自动刷新。
- 刷新时把 `credit_balance` 设置为 48000。
- 上月剩余积分清零，不叠加。
- 记录 `monthly_refresh` 流水。

## 错误处理

- 积分不足：返回 `license_credit_insufficient`。
- 授权停用：沿用 `license_disabled`。
- 授权过期：沿用 `license_expired`。
- 预扣成功但云调用失败：必须 refund。
- 客户端断网：不允许本地离线扣积分后继续云调用。

## 测试计划

后端测试：

- 创建试用版授权自动获得 1300 积分。
- 创建月付版授权自动获得 48000 积分。
- 创建年会员授权自动获得 48000 积分。
- 飞影生成 10 秒扣 150 积分。
- 积分不足时阻止生成。
- 生成失败后退回预扣积分。
- 年会员刷新周期时余额重置为 48000，不结转。
- 后台手动加减积分有审计记录。

客户端测试：

- 云端调用前必须调用积分预扣接口。
- 预扣失败不调用飞影/阿里云。
- 预扣成功后云调用失败会请求退回积分。
- UI 显示客户可读的积分不足提示。

后台 UI 测试：

- 创建授权表单显示“赠送积分”。
- 套餐切换自动填默认积分。
- 授权列表显示剩余积分、本月已用和操作按钮。
- 积分明细不显示原始 JSON。

## 第一版实施范围

第一版只做“后台手动管理 + 客户端自动扣费”：

- 不接支付网关。
- 不做自动发票。
- 不做复杂套餐权益。
- 不做多级代理分销。
- 不做公网支付回调。

这样可以先支持售卖和成本控制，后续再接自动购买、自动续费和客户自助充值。
