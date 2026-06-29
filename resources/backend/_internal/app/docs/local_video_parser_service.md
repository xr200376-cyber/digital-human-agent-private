# 本地视频解析服务

本功能用于在 Aivo 工作台里粘贴公开视频链接后，自动尝试解析可下载的视频文件，再交给 ffmpeg 和 FunASR / Paraformer 转写成文案。

## 工作方式

1. 用户在“IP深度学习”卡片点击“打开视频链接”。
2. 系统调用内置本地解析器，优先使用 `yt-dlp` 解析公开视频链接。
3. 如果解析到视频文件，系统下载到 `storage/projects/{project_id}/reference_collections/`。
4. 系统抽取音频并转写成脚本文案。
5. 如果解析失败，界面显示中文失败原因，并提示先手动下载视频后上传。

## 限制

- 不自动登录任何平台。
- 不绕过验证码、权限、会员、私密内容或 DRM。
- 不保证所有抖音、小红书、快手、视频号链接都能解析。
- 平台规则变化时，可能需要升级 `yt-dlp`。

## 设置项

- `VIDEO_PARSER_ENABLED=true`
- `VIDEO_PARSER_ENGINE=yt_dlp`
- `VIDEO_PARSER_YTDLP_PATH=`：留空时使用系统 PATH 中的 `yt-dlp`。
- `VIDEO_PARSER_TIMEOUT_SECONDS=120`
- `VIDEO_PARSER_MAX_DOWNLOAD_MB=500`

## 文件策略

解析和转写产生的视频、音频、文案只写入本地 `storage/`，不要提交到仓库或打包进安装包。
