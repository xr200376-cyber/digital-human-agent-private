# 分镜工作流设计文档

**日期：** 2026-05-27
**状态：** 已批准，待实现

---

## 背景

现有工作流支持完整文案 → 单段数字人口播视频。本次新增**分镜模式**：把文案拆成若干组（每组 1-2 句），每组独立生成分镜图 + 音频 + 视频片段，最终可合并为一个完整视频。

---

## 用户流程

```
[现有流程]
提取文案 → 改写 → 确认文案
                        ↓
              ┌─────────┴──────────┐
              │                    │
          普通口播模式          分镜模式（新）
              │                    │
         （现有流程）         拆分文案为 scenes
                                   │
                            [每个 scene 并发]
                            LLM 生成插图 prompt
                                   │
                            GPT Image 2 (图生图)
                            → 分镜图（失败用豆包）
                                   │
                            TTS 生成该句音频
                                   │
                            可灵 Avatar 生成视频片段
                                   │
                            [所有 scene 完成]
                                   │
                            前端展示分镜列表（可单独预览）
                                   │
                            一键合并 → 完整视频
```

---

## 数据模型

### SceneState

| 字段 | 类型 | 说明 |
|------|------|------|
| `scene_id` | str | UUID |
| `session_id` | str | 关联 WorkflowState.session_id |
| `index` | int | 场景顺序（0, 1, 2...） |
| `text` | str | 原始文案（1-2句，不修改） |
| `illustration_prompt` | str | LLM 生成的插图描述 prompt |
| `image_path` | str \| None | 生成的分镜图本地路径 |
| `image_status` | str | `pending` / `processing` / `succeed` / `failed` |
| `image_error` | str \| None | 图片生成错误信息 |
| `audio_path` | str \| None | TTS 音频本地路径 |
| `audio_status` | str | `pending` / `succeed` / `failed` |
| `video_url` | str \| None | 可灵生成的视频 URL |
| `video_status` | str | `pending` / `processing` / `succeed` / `failed` |
| `video_error` | str \| None | 视频生成错误信息 |

### StoryboardSession

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | str | 与 WorkflowState.session_id 相同 |
| `reference_image_path` | str | 复用 WorkflowState.avatar_image_path |
| `scenes` | list[SceneState] | 所有分镜场景 |
| `merged_video_path` | str \| None | 合并后视频本地路径 |
| `merged_video_url` | str \| None | 合并后可访问 URL |
| `status` | str | `init` / `processing` / `done` / `failed` |

### Store

- **InMemory**：`dict[session_id, StoryboardSession]`
- **MySQL**：新增两张表
  - `storyboard_sessions`（主表）
  - `storyboard_scenes`（scene 列表，`session_id` + `index` 联合主键）

---

## 新增文件

| 文件 | 职责 |
|------|------|
| `storyboard_state.py` | StoryboardSession、SceneState 数据类 + Store（InMemory / MySQL） |
| `text_splitter.py` | 把文案拆分为 1-2 句一组的列表（按 `。！？\n` 断句） |
| `image_gen_service.py` | GPT Image 2 图生图（主）+ 豆包图生图（备）|
| `storyboard_routes.py` | FastAPI 路由，在 server.py 中 `include_router` 挂载 |
| `video_merge_service.py` | 用 ffmpeg 把多段视频 URL/路径拼接为一个视频文件 |

---

## API 路由

所有路由挂载在 `tags=["storyboard"]`，基路径 `/workflow/{session_id}/storyboard`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/init` | 拆分 final_text → 创建 StoryboardSession + scenes，返回 scene 列表 |
| POST | `/generate-all` | 后台并发生成所有 scene（image → audio → video） |
| GET  | `/status` | 返回 StoryboardSession 整体状态 + 每个 scene 状态 |
| POST | `/scene/{index}/retry` | 重试指定 scene（从 image 步骤开始） |
| POST | `/merge` | 所有 scene video_status == succeed 后合并视频，返回 merged_video_url |

### 前置条件

- `/init`：WorkflowState.current_step == `confirmed` 且 `avatar_image_path` 不为空
- `/generate-all`：StoryboardSession 已创建（调用过 `/init`）
- `/merge`：所有 scenes 的 `video_status == succeed`

---

## 分镜图生成方案

### 图生图流程（每个 scene）

1. **LLM 生成 prompt**（Kimi/Moonshot）

   输入：scene.text
   输出：一段英文 prompt，格式要求：
   - 描述该句话的视觉场景（e.g. `"two dogs fighting fiercely"`）
   - 包含约束：`"keep the main character and background unchanged, add a small illustrative scene element in the corner area without covering the person's face"`

2. **GPT Image 2 图生图**（OpenAI Images Edit API）

   - 接口：`POST /v1/images/edits`
   - 输入：原图（reference_image）+ prompt（上一步生成）
   - 输出：含插图的分镜图

3. **豆包兜底**（GPT Image 2 失败时）

   - 使用豆包图像编辑 API，同样传原图 + prompt

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | GPT Image 2 鉴权 |
| `OPENAI_API_BASE` | 可选，自定义 base URL |
| `DOUBAO_API_KEY` | 豆包鉴权 |
| `DOUBAO_IMAGE_MODEL` | 豆包图像模型 ID |

---

## 文案拆分规则

- 按 `。！？!?\n` 分句
- 优先每 2 句一组；最后一组剩 1 句时独立成组
- 每组超过 200 字时强制拆分（保证 TTS 音频不过长）
- 空行和空句跳过

---

## 视频合并

- 工具：`ffmpeg`（subprocess 调用，无需 moviepy）
- 流程：下载各 scene 视频（远程 URL）到 `generated/{session_id}_scene_{index}.mp4` → 生成 concat 列表文件 → `ffmpeg -f concat -safe 0` 拼接
- 输出：`generated/{session_id}_merged.mp4`，通过 `/generated/*` 静态路由可访问

---

## 前端改动（Vue 3）

- confirm 步骤完成后，需先上传数字人参考图（复用现有 avatar-image 上传步骤），图片就绪后显示**"分镜模式"**按钮（与"生成音频"并列）
- 点击后进入分镜页：
  - 显示 scene 列表（序号 + 文案片段 + 状态指示）
  - "全部生成"按钮 → 调用 `/generate-all`
  - 每个 scene 卡片展示：分镜图预览、音频播放、视频播放、失败时重试按钮
  - 轮询 `/status` 更新进度
  - 全部成功后显示"合并视频"按钮
  - 合并完成展示最终视频 + 下载链接

---

## 错误处理

- 单个 scene 失败不影响其他 scene 继续生成
- 图片生成失败时自动切换豆包，豆包也失败则 scene 标记 `image_status=failed`
- merge 接口检查所有 scene 完成，有失败的 scene 时返回 409 并提示哪些 scene 未完成
- 所有后台任务异常均写回对应 scene 的 error 字段

---

## 不在本期范围

- 分镜顺序手动调整
- 单个 scene 替换参考图
- 分镜图手动编辑
- 多语言 TTS 声音选择（复用现有 TTS_VOICE 设置）
