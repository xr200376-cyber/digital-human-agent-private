# 参考平台内容采集器

## 目标

`IP深度学习` 卡片中的“打开视频链接”用于采集公开平台链接的参考信息，帮助用户把平台标题、文案、封面和公开视频信息带回当前工作台，再继续生成口播脚本。

## 当前支持

- 抖音 / Douyin
- 小红书
- 快手
- B站
- 视频号链接识别
- 通用网页

第一版只采集公开页面元数据：

- 平台
- 原始链接
- 跳转后的最终链接
- 标题
- 描述/文案
- 封面 URL
- 公开视频 URL
- 是否看起来可直接下载

## 不做的事情

- 不自动登录平台账号。
- 不绕过验证码、风控、付费墙、私密权限或 DRM。
- 不批量爬取。
- 不移除水印。
- 不把他人视频自动作为最终成片素材。

如果平台限制导致无法采集，系统会返回 `blocked` 状态，并提示用户手动下载参考视频后上传，或复制平台文案到输入框。

## 前端行为

在“数字人制作”页面：

1. 点击 `打开视频链接`。
2. 粘贴公开平台链接。
3. 成功时，采集内容会回填到 `IP深度学习` 输入框。
4. 如果脚本文案还是默认示例，系统会把采集到的标题/文案同步到 `视频文案编辑`。
5. 用户继续点击 `爆款文案` 或 `AI生成`，用当前云端大模型生成口播脚本。

## 后端 API

`POST /projects/{project_id}/reference-links/collect`

请求：

```json
{
  "url": "https://www.douyin.com/video/example",
  "metadata": {
    "fallback_text": "可选兜底文案"
  }
}
```

响应核心字段：

```json
{
  "status": "captured",
  "platform": "douyin",
  "title": "参考视频标题",
  "description": "参考文案",
  "cover_url": "https://example.com/cover.jpg",
  "video_url": "https://example.com/video.mp4",
  "content_text": "结构化采集文本",
  "script_seed": "用于生成脚本的种子文本",
  "downloadable": true
}
```

采集结果会保存到：

`storage/projects/{project_id}/reference_collections/{collection_id}/collection.json`

同时写入审计事件：

`reference_link.collected`
