# Aivo 桌面壳

这个 Electron 桌面壳会启动现有 FastAPI 后端，并以桌面软件的方式打开 Aivo 数字人口播工作台。它不重写后端，只负责本地启动、设置和日志查看。

## Windows 构建

在仓库根目录运行：

```powershell
cd desktop\electron
npm install
npm run dev
```

构建 Windows 安装包：

```powershell
npm run build:win
```

构建产物会输出到 `dist/desktop/`。

## 桌面壳功能

- 启动 `python -m uvicorn app.main:app`
- 打开 `http://127.0.0.1:8080/`
- 提供托盘入口：打开工作台、设置、重启、停止、日志和退出
- 提供设置页：运行模式、TTS、Pixelle、Wav2Lip、YYWav2Lip、MuseTalk、LatentSync、剪映和 Duix HTTP
- 默认以 `standard` 真实模式启动后端，也就是 `DRY_RUN=false`
- 如需试用占位流程，可在设置页切换为 `dry-run`
- 支持一键校验、红黄绿状态、`.env` 输出复制和对齐报告
- 把后端日志写入 `storage/desktop/backend.log`

## 边界

桌面构建不包含模型权重、生成媒体、客户上传素材或 `storage` 产物。真实引擎仍需要在桌面版设置页中填写本机路径。
