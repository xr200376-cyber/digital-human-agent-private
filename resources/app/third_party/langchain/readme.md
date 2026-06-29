# 数字人内容工作流

这份项目现在只保留一条流程：

网页 URL / 上传视频 / 直接输入文本
→ 提取或确认文本
→ AI 改写
→ 确认文本
→ 上传人物图 + 生成语音
→ 异步生成可灵数字人口播视频

## 主要模块

- `server.py`
  工作流后端接口，提供 `/workflow/*`
- `frontend/`
  分步式 H5 界面
- `content_extraction.py`
  网页内容提取、视频转写、抖音分享解析
- `text_rewrite.py`
  调用 Moonshot/Kimi 做文本改写
- `tts_service.py`
  使用 Edge TTS 生成中文音频
- `kling_service.py`
  调用可灵的 Avatar 接口
- `workflow_state.py`
  内存态工作流状态
- `moonshot_service.py`
  `.env` 加载与 Kimi 客户端初始化

## 环境要求

- Python 3.10+
- `uv`
- Node.js 18+（仅前端开发需要）
- `ffmpeg`（视频转写需要）

## 安装

```bash
uv sync
cp .env.example .env
```

至少配置：

```env
MOONSHOT_API_KEY=...
KLING_ACCESS_KEY_ID=...
KLING_ACCESS_KEY_SECRET=...
```

可选：

```env
TTS_VOICE=zh-CN-XiaoxiaoNeural
KLING_API_BASE_URL=https://api.klingai.com
KLING_PRINT_JWT=0
KLING_DEBUG_HTTP=0
WORKFLOW_STORE_BACKEND=mysql
WORKFLOW_DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/digital_human_workflow
WORKFLOW_MYSQL_TABLE=workflow_sessions
```

说明：

- 默认网关已改为 `https://api.klingai.com`
- 如果你的可灵账号明确要求新加坡网关，再手动覆盖 `KLING_API_BASE_URL=https://api-singapore.klingai.com`
- 排查鉴权时可临时设置 `KLING_PRINT_JWT=1`，后端控制台会打印完整 JWT，排查后建议改回 `0`
- 排查请求头时可临时设置 `KLING_DEBUG_HTTP=1`，后端控制台会打印 Authorization 是否实际带出
- `WORKFLOW_STORE_BACKEND=mysql` 会把工作流会话写入 MySQL，后端重启后仍可查询旧 session

MySQL 首次使用前先建库：

```sql
CREATE DATABASE IF NOT EXISTS digital_human_workflow
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

应用启动时会自动创建 `workflow_sessions` 表。

前端依赖：

```bash
cd frontend
npm install
```

## 启动

后端：

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8000
```

接口文档：

- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

前端：

```bash
cd frontend
npm run dev
```

默认地址：

- [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 保留的工作流接口

- `POST /workflow/start`
- `POST /workflow/upload`
- `GET /rewrite-styles`
- `POST /workflow/{session_id}/rewrite`
- `POST /workflow/{session_id}/confirm`
- `POST /workflow/{session_id}/audio`
- `POST /workflow/{session_id}/avatar-image`
- `POST /workflow/{session_id}/video`
- `GET /workflow/{session_id}/status`
- `GET /workflow/sessions`

## 说明

- 项目已经移除聊天/RAG/多角色/联网检索相关代码
- 启动工作流后端时，不会再初始化 Hugging Face 向量模型
