# Simple Desktop Navigation Design

## Goal

Simplify the desktop UI so users see a small set of task-oriented entry points instead of every internal workflow page.

## Navigation

The left sidebar will show only these primary entries:

- 工作台
- 模型设置
- 项目
- 数字人制作
- 视频生产
- 任务与发布
- 环境检查

Existing internal pages remain available through workflow buttons and programmatic transitions, but they will no longer appear as top-level sidebar items.

## Model Settings

The existing model-center view becomes "模型设置". Its top actions will be simplified:

- 刷新
- 配置云模型
- 本地模型

The cloud and local model modals remain, but the visible language stops repeating "模型选择 / 大模型设置 / 添加本地模型" as separate concepts.

## Active State

When internal pages open, the sidebar highlights their nearest primary group:

- 数字人详情, 源视频数字人, 声音档案 -> 数字人制作
- 参考视频, 脚本改写, 批量生产, 创建视频 -> 视频生产
- 任务详情, 结果下载, 质量中心, 任务队列, 发布交接 -> 任务与发布

## Verification

Tests should confirm the simplified nav labels, hidden intermediate nav labels, model page wording, and JS group mapping. Browser checks should verify the desktop `8080` page serves the updated sidebar and model settings controls.
