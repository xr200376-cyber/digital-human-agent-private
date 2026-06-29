# 半自动收款订单与自动发货设计

## 背景

当前商业后台已经具备客户、授权码、设备绑定、积分账本、版本更新和审计日志能力。由于微信 Native 支付暂未开通，第一版不接微信支付 API，改为“客户手动付款、后台人工确认、系统自动发货”的交付链路。后续开通 JSAPI 或 Native 支付时，可以把支付成功回调接入同一套订单和发货逻辑。

## 目标

- 客户可以自助选择套餐或充值包并提交订单。
- 客户付款后提交微信号、手机号、付款备注或付款截图。
- 运营后台可以查看订单并人工确认收款。
- 确认收款后系统自动创建客户、生成授权码、恢复正式版或充值积分。
- 订单、发货、积分变动、驳回和补发都记录审计日志。

## 非目标

- 第一版不接微信 Native、JSAPI、小程序支付或 H5 支付。
- 第一版不自动识别到账截图，不通过个人微信收款记录做自动对账。
- 第一版不做发票、优惠券、代理分佣、退款自动化和复杂会员等级。

## 套餐和积分规则

- 试用版：1300 积分。
- 月付版：48000 积分。
- 年会员：每月刷新 48000 积分，不结转到下月。
- 充值包：按后台配置的充值包发放固定积分。
- 飞影成本基准为 10 积分/秒，对客户扣费为 15 积分/秒，现有积分扣费逻辑保持不变。

## 客户购买流程

1. 客户打开购买页。
2. 选择套餐或充值包。
3. 填写联系人信息：微信号必填，手机号可选，已有授权码可选。
4. 页面展示应付金额、收款码和付款备注建议。
5. 客户付款后提交付款凭证：截图可选，付款备注或转账时间至少填一项。
6. 系统创建订单，状态为 `pending_review`，提示客户等待确认。
7. 后台确认收款后，客户订单页展示授权码、套餐、积分余额和下载地址。

## 后台处理流程

后台新增“订单”页，列表显示：

- 订单号
- 客户姓名或微信号
- 套餐/充值包
- 应付金额
- 订单状态
- 付款凭证
- 关联授权码
- 创建时间和确认时间

后台动作：

- 确认收款并发货：执行自动发货。
- 驳回订单：填写原因，状态改为 `rejected`。
- 标记待补充凭证：状态改为 `needs_evidence`。
- 补发：仅对已付款但发货失败的订单重新执行发货。

## 自动发货规则

系统根据订单类型选择发货路径：

- 新购试用版、月付版、年会员：如果没有关联授权码，则先创建或复用客户，再生成授权码。
- 已有授权码续费或充值：校验授权码存在后给该授权码充值积分或恢复对应套餐。
- 月付版：授权状态设为 `active`，积分余额和月度赠送积分设为 48000。
- 年会员：授权状态设为 `active`，套餐设为 `yearly`，本周期积分设为 48000，后续按现有月度刷新逻辑补足。
- 充值包：调用现有积分调整逻辑增加积分，不改变套餐。

发货成功后订单状态改为 `fulfilled`。发货失败时订单状态改为 `fulfillment_failed`，错误原因写入订单，后台可以重试。

## 数据模型

新增 `orders` 存储集合，字段如下：

- `order_id`
- `order_no`
- `customer_id`
- `license_id`
- `license_key_preview`
- `contact_name`
- `wechat`
- `phone`
- `product_type`: `trial`, `monthly`, `yearly`, `credit_pack`
- `product_name`
- `amount_cents`
- `currency`: 默认 `CNY`
- `credit_grant`
- `status`: `draft`, `pending_review`, `needs_evidence`, `paid`, `fulfilled`, `fulfillment_failed`, `rejected`, `cancelled`
- `payment_method`: `wechat_manual`
- `payment_note`
- `payment_time`
- `evidence_file_id`
- `operator_note`
- `fulfillment_error`
- `created_at`
- `updated_at`
- `paid_at`
- `fulfilled_at`
- `rejected_at`

新增 `manual_payment_evidence` 存储集合，字段如下：

- `evidence_id`
- `order_id`
- `original_filename`
- `stored_path`
- `content_type`
- `size_bytes`
- `created_at`

## API 设计

公开客户 API：

- `GET /shop/plans`：返回可购买套餐和充值包。
- `POST /shop/orders`：创建订单。
- `GET /shop/orders/{order_no}`：查询订单状态和发货结果。
- `POST /shop/orders/{order_no}/evidence`：提交付款凭证或备注。

后台 API：

- `GET /admin/api/orders`：订单列表。
- `GET /admin/api/orders/{order_id}`：订单详情。
- `POST /admin/api/orders/{order_id}/confirm-payment`：确认收款并自动发货。
- `POST /admin/api/orders/{order_id}/reject`：驳回订单。
- `POST /admin/api/orders/{order_id}/request-evidence`：要求补充凭证。
- `POST /admin/api/orders/{order_id}/retry-fulfillment`：重试发货。

## 页面设计

客户购买页：

- 顶部展示产品名称和购买说明。
- 中间展示套餐卡片：试用版、月付版、年会员、充值包。
- 下方展示联系人表单和收款码。
- 提交后展示订单状态和授权码结果。

后台订单页：

- 集成到现有商业后台。
- 新增“订单”标签。
- 使用客户可读状态，不显示原始 JSON。
- 对 `pending_review` 和 `fulfillment_failed` 订单突出显示可处理动作。

## 安全和风控

- 后台确认收款接口必须要求管理员登录。
- 客户查询订单只通过不可猜测的 `order_no` 访问，不暴露内部自增 ID。
- 付款截图只允许图片格式，限制文件大小。
- 上传文件使用服务端生成文件名，不信任原始文件名。
- 授权码完整值只在发货结果中首次展示，后台列表默认只显示脱敏值。
- 确认收款、驳回、重试发货、积分变动都写审计日志。

## 错误处理

- 订单不存在：提示“订单不存在，请检查链接是否完整”。
- 凭证缺失：提示“请填写付款备注或上传付款截图”。
- 授权码不存在：提示“填写的授权码不存在，请检查后重试”。
- 已发货订单重复确认：直接返回现有发货结果，不重复加积分。
- 发货失败：保留订单和错误信息，允许后台重试。

## 测试计划

- 创建试用版订单后，后台确认收款可以生成授权码并发 1300 积分。
- 创建月付版订单后，后台确认收款可以生成授权码并发 48000 积分。
- 创建年会员订单后，后台确认收款可以生成授权码，设置年会员并发当前月 48000 积分。
- 已有授权码充值订单确认后只增加积分，不新建授权码。
- 重复确认已发货订单不会重复加积分。
- 驳回订单不会发货。
- 发货失败后可以重试。
- 上传非图片或过大凭证会被拒绝。
- 后台订单页不显示原始 JSON，订单状态文案客户可读。

## 后续自动支付升级

后续开通微信 JSAPI 或 Native 支付时，保留现有订单模型，新增：

- `payment_provider`
- `provider_trade_no`
- `prepay_id`
- `paid_callback_payload`
- `signature_verified_at`

自动支付版本会新增 `pending_payment` 状态。微信支付成功回调只负责把订单从 `pending_payment` 改为 `paid` 并触发同一套 `fulfill_order` 发货逻辑。
