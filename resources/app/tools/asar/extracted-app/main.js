const { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const APP_ROOT = resolveAppRoot();
const API_TIMEOUT_MS = 45000;
const MAX_BACKEND_LOG_BYTES = 2 * 1024 * 1024;
const MAX_BACKEND_LOG_CHUNK_BYTES = 64 * 1024;
const DEFAULT_SETTINGS = {
  runtimeMode: "standard",
  dryRun: false,
  backendHost: "127.0.0.1",
  backendPort: 8080,
  pythonPath: "python",
  storagePath: "storage",
  selected_preset: "custom",
  tts_provider: "dryrun",
  digital_human_engine: "auto",
  editing_output: "mp4_only",
  TTS_ENGINE: "dryrun",
  TTS_BASE_URL: "",
  TTS_DEFAULT_VOICE: "",
  COSYVOICE_URL: "",
  GPT_SOVITS_URL: "",
  PIXELLE_ENABLED: false,
  PIXELLE_BASE_URL: "http://127.0.0.1:8000",
  PIXELLE_SCRIPT_ENDPOINT: "/api/content/narration",
  PIXELLE_VIDEO_ENDPOINT: "/api/video/generate/sync",
  CLOUD_LIPSYNC_ENABLED: false,
  CLOUD_LIPSYNC_PROVIDER: "syncso",
  SYNCSO_BASE_URL: "https://api.sync.so",
  SYNCSO_API_KEY: "",
  SYNCSO_MODEL: "lipsync-2",
  SYNCSO_GENERATE_ENDPOINT: "/v2/generate",
  SYNCSO_TIMEOUT_SECONDS: 1200,
  SYNCSO_POLL_INTERVAL_SECONDS: 5,
  OMNIHUMAN_ENABLED: false,
  OMNIHUMAN_ACCESS_KEY: "",
  OMNIHUMAN_SECRET_KEY: "",
  OMNIHUMAN_ENDPOINT: "https://visual.volcengineapi.com",
  OMNIHUMAN_REGION: "cn-north-1",
  OMNIHUMAN_SERVICE: "cv",
  OMNIHUMAN_VERSION: "2024-06-06",
  OMNIHUMAN_REQ_KEY: "jimeng_realman_avatar_picture_omni_v15",
  OMNIHUMAN_OUTPUT_RESOLUTION: 1080,
  OMNIHUMAN_PROMPT: "自然口播，面带微笑，保持人物身份一致。",
  OMNIHUMAN_PE_FAST_MODE: false,
  OMNIHUMAN_TIMEOUT_SECONDS: 1200,
  OMNIHUMAN_POLL_INTERVAL_SECONDS: 5,
  TAVUS_ENABLED: false,
  TAVUS_BASE_URL: "https://tavusapi.com",
  TAVUS_API_KEY: "",
  TAVUS_REPLICA_ID: "",
  TAVUS_VIDEO_ENDPOINT: "/v2/videos",
  TAVUS_TIMEOUT_SECONDS: 1800,
  TAVUS_POLL_INTERVAL_SECONDS: 8,
  BAIDU_XILING_ENABLED: false,
  BAIDU_XILING_BASE_URL: "https://open.xiling.baidu.com",
  BAIDU_XILING_APP_ID: "",
  BAIDU_XILING_APP_KEY: "",
  BAIDU_XILING_FIGURE_ID: "",
  BAIDU_XILING_TTS_PERSON: "",
  BAIDU_XILING_WIDTH: 1080,
  BAIDU_XILING_HEIGHT: 1920,
  BAIDU_XILING_TRANSPARENT: false,
  BAIDU_XILING_TIMEOUT_SECONDS: 1200,
  BAIDU_XILING_POLL_INTERVAL_SECONDS: 5,
  HIFLY_ENABLED: false,
  HIFLY_BASE_URL: "https://hfw-api.hifly.cc",
  HIFLY_TOKEN: "",
  HIFLY_REQUIRED: false,
  HIFLY_POLL_INTERVAL_SECONDS: 5,
  HIFLY_TIMEOUT_SECONDS: 1800,
  CLOUD_VOICE_PROVIDER: "edge_tts_no_clone",
  CLOUD_VIDEO_PROVIDER: "local",
  DASHSCOPE_API_KEY: "",
  ALIYUN_BAILIAN_REGION: "cn-beijing",
  ALIYUN_VOICE_MODEL: "cosyvoice-v1",
  ELEVENLABS_API_KEY: "",
  AZURE_SPEECH_KEY: "",
  AZURE_SPEECH_ENDPOINT: "",
  CUSTOM_HTTP_TTS_BASE_URL: "",
  CUSTOM_HTTP_TTS_API_KEY: "",
  FAL_API_KEY: "",
  FAL_LATENTSYNC_MODEL: "fal-ai/latentsync",
  FAL_MUSETALK_MODEL: "fal-ai/musetalk",
  SELF_HOSTED_LIPSYNC_BASE_URL: "",
  SELF_HOSTED_LIPSYNC_API_KEY: "",
  WAV2LIP_ENABLED: false,
  WAV2LIP_ROOT: "third_party/Wav2Lip",
  WAV2LIP_CHECKPOINT: "checkpoints/wav2lip.pth",
  YY_WAV2LIP_ENABLED: false,
  YY_WAV2LIP_CHECKPOINT: "resource/checkpoints/yywav2lip.pth",
  YY_WAV2LIP_ROLE_MODEL_DIR: "",
  MUSETALK_ENABLED: false,
  MUSETALK_ROOT: "third_party/MuseTalk",
  MUSETALK_MODEL_DIR: "",
  LATENTSYNC_ENABLED: false,
  LATENTSYNC_ROOT: "third_party/LatentSync",
  LATENTSYNC_CHECKPOINT: "",
  LATENTSYNC_UNET_CONFIG: "",
  JIANYING_ENABLED: false,
  JIANYING_DRAFT_ROOT: "",
  DUIX_ENABLED: false,
  DUIX_BASE_URL: "http://127.0.0.1:8383"
};

let mainWindow = null;
let settingsWindow = null;
let tray = null;
let backendProcess = null;
let backendStopping = false;
let backendLogDisabled = false;

function resolveAppRoot() {
  if (process.env.AIVO_APP_ROOT) return process.env.AIVO_APP_ROOT;
  const devRoot = path.resolve(__dirname, "..", "..");
  if (fs.existsSync(path.join(devRoot, "app", "main.py"))) return devRoot;
  if (process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, "app", "main.py"))) {
    return process.resourcesPath;
  }
  return devRoot;
}

function settingsFile() {
  return path.join(app.getPath("userData"), "desktop-settings.json");
}

function seedSettingsCandidates() {
  const candidates = [];
  if (process.resourcesPath) {
    candidates.push(path.join(process.resourcesPath, "desktop-settings.seed.json"));
    candidates.push(path.join(process.resourcesPath, "storage", "desktop", "desktop_settings.json"));
  }
  candidates.push(path.join(APP_ROOT, "desktop-settings.seed.json"));
  candidates.push(path.join(APP_ROOT, "storage", "desktop", "desktop_settings.json"));
  return candidates;
}

function readSeedSettings() {
  for (const candidate of seedSettingsCandidates()) {
    try {
      if (!candidate || !fs.existsSync(candidate)) continue;
      const text = fs.readFileSync(candidate, "utf8").replace(/^\uFEFF/, "");
      return JSON.parse(text);
    } catch (_error) {
      // Try the next seed candidate.
    }
  }
  return {};
}

function mergeSettings(raw) {
  const merged = {
    ...DEFAULT_SETTINGS,
    ...raw,
    runtimeMode: raw.runtimeMode || raw.runtime_mode || (raw.dryRun ? "dry-run" : DEFAULT_SETTINGS.runtimeMode)
  };
  merged.dryRun = isDryRunMode(merged);
  if (raw.pixelleUrl && !raw.PIXELLE_BASE_URL) merged.PIXELLE_BASE_URL = raw.pixelleUrl;
  if (raw.duixUrl && !raw.DUIX_BASE_URL) merged.DUIX_BASE_URL = raw.duixUrl;
  if (raw.enginePaths) {
    if (raw.enginePaths.jianyingDraftRoot && !raw.JIANYING_DRAFT_ROOT) merged.JIANYING_DRAFT_ROOT = raw.enginePaths.jianyingDraftRoot;
    if (raw.enginePaths.musetalkCliPath && !raw.MUSETALK_ROOT) merged.MUSETALK_ROOT = path.dirname(path.dirname(raw.enginePaths.musetalkCliPath));
    if (raw.enginePaths.latentsyncCliPath && !raw.LATENTSYNC_ROOT) merged.LATENTSYNC_ROOT = path.dirname(path.dirname(raw.enginePaths.latentsyncCliPath));
  }
  if (raw.modelPaths) {
    if (raw.modelPaths.latentsyncCkptPath && !raw.LATENTSYNC_CHECKPOINT) merged.LATENTSYNC_CHECKPOINT = raw.modelPaths.latentsyncCkptPath;
    if (raw.modelPaths.latentsyncConfigPath && !raw.LATENTSYNC_UNET_CONFIG) merged.LATENTSYNC_UNET_CONFIG = raw.modelPaths.latentsyncConfigPath;
    if (raw.modelPaths.musetalkModelDir && !raw.MUSETALK_MODEL_DIR) merged.MUSETALK_MODEL_DIR = raw.modelPaths.musetalkModelDir;
    if (raw.modelPaths.wav2lipCheckpoint && !raw.WAV2LIP_CHECKPOINT) merged.WAV2LIP_CHECKPOINT = raw.modelPaths.wav2lipCheckpoint;
    if (raw.modelPaths.yyWav2LipCheckpoint && !raw.YY_WAV2LIP_CHECKPOINT) merged.YY_WAV2LIP_CHECKPOINT = raw.modelPaths.yyWav2LipCheckpoint;
  }
  return merged;
}

function isDryRunMode(settings) {
  return (settings.runtimeMode || settings.runtime_mode) === "dry-run" || settings.dryRun === true;
}

function boolEnv(value) {
  return value ? "true" : "false";
}

function readSettings() {
  try {
    const text = fs.readFileSync(settingsFile(), "utf8").replace(/^\uFEFF/, "");
    return mergeSettings(JSON.parse(text));
  } catch (error) {
    const seed = readSeedSettings();
    if (Object.keys(seed).length > 0) {
      const mergedSeed = mergeSettings(seed);
      try {
        fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
        fs.writeFileSync(settingsFile(), JSON.stringify(mergedSeed, null, 2), "utf8");
      } catch (_writeError) {
        // Seed settings can still be used for this session.
      }
      return mergedSeed;
    }
    try {
      appendBackendLog(`[desktop] settings read failed path=${settingsFile()} error=${error.message}\n`, mergeSettings({}));
    } catch (_logError) {
      // Ignore logging failures while settings are not available yet.
    }
    return mergeSettings({});
  }
}

function saveSettings(settings) {
  const merged = mergeSettings(settings || {});
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(merged, null, 2), "utf8");
  return merged;
}

function resolveStoragePath(settings) {
  const storagePath = settings.storagePath || DEFAULT_SETTINGS.storagePath;
  return path.isAbsolute(storagePath) ? storagePath : path.join(APP_ROOT, storagePath);
}

function readInternalProviderSecrets(settings) {
  const allowedKeys = new Set([
    "AIVO_PARSER_BASE_URL",
    "AIVO_PARSER_ENDPOINT",
    "AIVO_PARSER_TOKEN",
    "TIKHUB_BASE_URL",
    "TIKHUB_API_KEY",
    "TIKHUB_DOUYIN_ENDPOINT",
    "ISTERO_BASE_URL",
    "ISTERO_API_KEY",
    "ISTERO_DOUYIN_ENDPOINT",
    "EVIL0CTAL_DOUYIN_API_BASE_URL",
    "EVIL0CTAL_DOUYIN_API_ENDPOINT",
    "DASHSCOPE_API_KEY",
    "HIFLY_TOKEN",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY"
  ]);
  const secretPath = path.join(resolveStoragePath(settings), "desktop", "internal_provider_secrets.json");
  try {
    if (!fs.existsSync(secretPath)) return {};
    const raw = JSON.parse(fs.readFileSync(secretPath, "utf8").replace(/^\uFEFF/, ""));
    const secrets = {};
    for (const [key, value] of Object.entries(raw || {})) {
      if (allowedKeys.has(key) && value !== undefined && value !== null && String(value).trim()) {
        secrets[key] = String(value);
      }
    }
    return secrets;
  } catch (_error) {
    return {};
  }
}

function backendLogPath(settings = readSettings()) {
  return path.join(resolveStoragePath(settings), "desktop", "backend.log");
}

function trimBackendLogChunk(line) {
  const text = String(line ?? "");
  if (Buffer.byteLength(text, "utf8") <= MAX_BACKEND_LOG_CHUNK_BYTES) return text;
  return `${text.slice(0, MAX_BACKEND_LOG_CHUNK_BYTES)}\n[desktop] backend log chunk truncated\n`;
}

function rotateBackendLogIfNeeded(logPath) {
  try {
    if (!fs.existsSync(logPath)) return;
    const stat = fs.statSync(logPath);
    if (stat.size <= MAX_BACKEND_LOG_BYTES) return;
    const rotatedPath = `${logPath}.1`;
    try {
      if (fs.existsSync(rotatedPath)) fs.unlinkSync(rotatedPath);
    } catch (_error) {
      // Rotation cleanup is best-effort.
    }
    try {
      fs.renameSync(logPath, rotatedPath);
    } catch (_error) {
      fs.writeFileSync(logPath, "", "utf8");
    }
  } catch (_error) {
    // Log rotation must never stop the desktop shell.
  }
}

function appendBackendLog(line, settings = readSettings()) {
  if (backendLogDisabled) return;
  try {
    const logPath = backendLogPath(settings);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    rotateBackendLogIfNeeded(logPath);
    fs.appendFileSync(logPath, trimBackendLogChunk(line), "utf8");
  } catch (error) {
    if (error && error.code === "ENOSPC") {
      backendLogDisabled = true;
    }
    try {
      console.error("[desktop] backend log write failed", error);
    } catch (_consoleError) {
      // Ignore console failures too.
    }
  }
}

function backendUrl(settings = readSettings()) {
  return `http://${settings.backendHost}:${settings.backendPort}`;
}

function backendEnv(settings) {
  const internalProviderSecrets = readInternalProviderSecrets(settings);
  return {
    ...process.env,
    RUNTIME_MODE: settings.runtimeMode,
    DRY_RUN: isDryRunMode(settings) ? "true" : "false",
    STORAGE_DIR: settings.storagePath,
    TTS_ENGINE: settings.TTS_ENGINE || "",
    TTS_BASE_URL: settings.TTS_BASE_URL || "",
    TTS_DEFAULT_VOICE: settings.TTS_DEFAULT_VOICE || "",
    COSYVOICE_URL: settings.COSYVOICE_URL || "",
    GPT_SOVITS_URL: settings.GPT_SOVITS_URL || "",
    PIXELLE_ENABLED: boolEnv(settings.PIXELLE_ENABLED),
    PIXELLE_BASE_URL: settings.PIXELLE_BASE_URL || "",
    PIXELLE_SCRIPT_ENDPOINT: settings.PIXELLE_SCRIPT_ENDPOINT || "",
    PIXELLE_VIDEO_ENDPOINT: settings.PIXELLE_VIDEO_ENDPOINT || "",
    CLOUD_LIPSYNC_ENABLED: boolEnv(settings.CLOUD_LIPSYNC_ENABLED),
    CLOUD_LIPSYNC_PROVIDER: settings.CLOUD_LIPSYNC_PROVIDER || "syncso",
    SYNCSO_BASE_URL: settings.SYNCSO_BASE_URL || "",
    SYNCSO_API_KEY: settings.SYNCSO_API_KEY || "",
    SYNCSO_MODEL: settings.SYNCSO_MODEL || "",
    SYNCSO_GENERATE_ENDPOINT: settings.SYNCSO_GENERATE_ENDPOINT || "",
    SYNCSO_TIMEOUT_SECONDS: String(settings.SYNCSO_TIMEOUT_SECONDS || 1200),
    SYNCSO_POLL_INTERVAL_SECONDS: String(settings.SYNCSO_POLL_INTERVAL_SECONDS || 5),
    OMNIHUMAN_ENABLED: boolEnv(settings.OMNIHUMAN_ENABLED),
    OMNIHUMAN_ACCESS_KEY: settings.OMNIHUMAN_ACCESS_KEY || "",
    OMNIHUMAN_SECRET_KEY: settings.OMNIHUMAN_SECRET_KEY || "",
    OMNIHUMAN_ENDPOINT: settings.OMNIHUMAN_ENDPOINT || "",
    OMNIHUMAN_REGION: settings.OMNIHUMAN_REGION || "",
    OMNIHUMAN_SERVICE: settings.OMNIHUMAN_SERVICE || "",
    OMNIHUMAN_VERSION: settings.OMNIHUMAN_VERSION || "",
    OMNIHUMAN_REQ_KEY: settings.OMNIHUMAN_REQ_KEY || "",
    OMNIHUMAN_OUTPUT_RESOLUTION: String(settings.OMNIHUMAN_OUTPUT_RESOLUTION || 1080),
    OMNIHUMAN_PROMPT: settings.OMNIHUMAN_PROMPT || "",
    OMNIHUMAN_PE_FAST_MODE: boolEnv(settings.OMNIHUMAN_PE_FAST_MODE),
    OMNIHUMAN_TIMEOUT_SECONDS: String(settings.OMNIHUMAN_TIMEOUT_SECONDS || 1200),
    OMNIHUMAN_POLL_INTERVAL_SECONDS: String(settings.OMNIHUMAN_POLL_INTERVAL_SECONDS || 5),
    TAVUS_ENABLED: boolEnv(settings.TAVUS_ENABLED),
    TAVUS_BASE_URL: settings.TAVUS_BASE_URL || "",
    TAVUS_API_KEY: settings.TAVUS_API_KEY || "",
    TAVUS_REPLICA_ID: settings.TAVUS_REPLICA_ID || "",
    TAVUS_VIDEO_ENDPOINT: settings.TAVUS_VIDEO_ENDPOINT || "",
    TAVUS_TIMEOUT_SECONDS: String(settings.TAVUS_TIMEOUT_SECONDS || 1800),
    TAVUS_POLL_INTERVAL_SECONDS: String(settings.TAVUS_POLL_INTERVAL_SECONDS || 8),
    BAIDU_XILING_ENABLED: boolEnv(settings.BAIDU_XILING_ENABLED),
    BAIDU_XILING_BASE_URL: settings.BAIDU_XILING_BASE_URL || "https://open.xiling.baidu.com",
    BAIDU_XILING_APP_ID: settings.BAIDU_XILING_APP_ID || "",
    BAIDU_XILING_APP_KEY: settings.BAIDU_XILING_APP_KEY || "",
    BAIDU_XILING_FIGURE_ID: settings.BAIDU_XILING_FIGURE_ID || "",
    BAIDU_XILING_TTS_PERSON: settings.BAIDU_XILING_TTS_PERSON || "",
    BAIDU_XILING_WIDTH: String(settings.BAIDU_XILING_WIDTH || 1080),
    BAIDU_XILING_HEIGHT: String(settings.BAIDU_XILING_HEIGHT || 1920),
    BAIDU_XILING_TRANSPARENT: boolEnv(settings.BAIDU_XILING_TRANSPARENT),
    BAIDU_XILING_TIMEOUT_SECONDS: String(settings.BAIDU_XILING_TIMEOUT_SECONDS || 1200),
    BAIDU_XILING_POLL_INTERVAL_SECONDS: String(settings.BAIDU_XILING_POLL_INTERVAL_SECONDS || 5),
    HIFLY_ENABLED: boolEnv(settings.HIFLY_ENABLED),
    HIFLY_BASE_URL: settings.HIFLY_BASE_URL || "https://hfw-api.hifly.cc",
    HIFLY_TOKEN: settings.HIFLY_TOKEN || "",
    HIFLY_REQUIRED: boolEnv(settings.HIFLY_REQUIRED),
    HIFLY_POLL_INTERVAL_SECONDS: String(settings.HIFLY_POLL_INTERVAL_SECONDS || 5),
    HIFLY_TIMEOUT_SECONDS: String(settings.HIFLY_TIMEOUT_SECONDS || 1800),
    CLOUD_VOICE_PROVIDER: settings.CLOUD_VOICE_PROVIDER || "edge_tts_no_clone",
    CLOUD_VIDEO_PROVIDER: settings.CLOUD_VIDEO_PROVIDER || "local",
    DASHSCOPE_API_KEY: settings.DASHSCOPE_API_KEY || "",
    ALIYUN_BAILIAN_REGION: settings.ALIYUN_BAILIAN_REGION || "cn-beijing",
    ALIYUN_VOICE_MODEL: settings.ALIYUN_VOICE_MODEL || "cosyvoice-v1",
    ELEVENLABS_API_KEY: settings.ELEVENLABS_API_KEY || "",
    AZURE_SPEECH_KEY: settings.AZURE_SPEECH_KEY || "",
    AZURE_SPEECH_ENDPOINT: settings.AZURE_SPEECH_ENDPOINT || "",
    CUSTOM_HTTP_TTS_BASE_URL: settings.CUSTOM_HTTP_TTS_BASE_URL || "",
    CUSTOM_HTTP_TTS_API_KEY: settings.CUSTOM_HTTP_TTS_API_KEY || "",
    FAL_API_KEY: settings.FAL_API_KEY || "",
    FAL_LATENTSYNC_MODEL: settings.FAL_LATENTSYNC_MODEL || "fal-ai/latentsync",
    FAL_MUSETALK_MODEL: settings.FAL_MUSETALK_MODEL || "fal-ai/musetalk",
    SELF_HOSTED_LIPSYNC_BASE_URL: settings.SELF_HOSTED_LIPSYNC_BASE_URL || "",
    SELF_HOSTED_LIPSYNC_API_KEY: settings.SELF_HOSTED_LIPSYNC_API_KEY || "",
    WAV2LIP_ENABLED: boolEnv(settings.WAV2LIP_ENABLED),
    WAV2LIP_ROOT: settings.WAV2LIP_ROOT || "",
    WAV2LIP_CHECKPOINT: settings.WAV2LIP_CHECKPOINT || "",
    YY_WAV2LIP_ENABLED: boolEnv(settings.YY_WAV2LIP_ENABLED),
    YY_WAV2LIP_CHECKPOINT: settings.YY_WAV2LIP_CHECKPOINT || "",
    YY_WAV2LIP_ROLE_MODEL_DIR: settings.YY_WAV2LIP_ROLE_MODEL_DIR || "",
    MUSETALK_ENABLED: boolEnv(settings.MUSETALK_ENABLED),
    MUSETALK_ROOT: settings.MUSETALK_ROOT || "",
    MUSETALK_SOURCE_DIR: settings.MUSETALK_ROOT || "",
    MUSETALK_MODEL_DIR: settings.MUSETALK_MODEL_DIR || "",
    LATENTSYNC_ENABLED: boolEnv(settings.LATENTSYNC_ENABLED),
    LATENTSYNC_ROOT: settings.LATENTSYNC_ROOT || "",
    LATENTSYNC_SOURCE_DIR: settings.LATENTSYNC_ROOT || "",
    LATENTSYNC_CHECKPOINT: settings.LATENTSYNC_CHECKPOINT || "",
    LATENTSYNC_CKPT_PATH: settings.LATENTSYNC_CHECKPOINT || "",
    LATENTSYNC_UNET_CONFIG: settings.LATENTSYNC_UNET_CONFIG || "",
    LATENTSYNC_CONFIG_PATH: settings.LATENTSYNC_UNET_CONFIG || "",
    JIANYING_ENABLED: boolEnv(settings.JIANYING_ENABLED),
    JIANYING_DRAFT_ROOT: settings.JIANYING_DRAFT_ROOT || "",
    DUIX_ENABLED: boolEnv(settings.DUIX_ENABLED),
    DUIX_BASE_URL: settings.DUIX_BASE_URL || "",
    ...internalProviderSecrets
  };
}

function backendStatus() {
  const settings = readSettings();
  return {
    running: Boolean(backendProcess && !backendProcess.killed),
    pid: backendProcess ? backendProcess.pid : null,
    url: backendUrl(settings),
    appRoot: APP_ROOT,
    logPath: backendLogPath(settings),
    runtimeMode: settings.runtimeMode,
    dryRun: isDryRunMode(settings)
  };
}

function backendUvicornArgs(settings) {
  return [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    settings.backendHost,
    "--port",
    String(settings.backendPort)
  ];
}

function resolveBackendCommand(settings) {
  const resourcesRoot = process.resourcesPath || APP_ROOT;
  const packagedBackend = path.join(resourcesRoot, "backend", "aivo_backend.exe");
  if (fs.existsSync(packagedBackend)) {
    return {
      command: packagedBackend,
      args: ["--host", settings.backendHost, "--port", String(settings.backendPort)],
      cwd: resourcesRoot,
      kind: "packaged-backend"
    };
  }

  const configuredPython = settings.pythonPath || "";
  if (configuredPython && configuredPython.toLowerCase() !== "python" && fs.existsSync(configuredPython)) {
    return {
      command: configuredPython,
      args: backendUvicornArgs(settings),
      cwd: APP_ROOT,
      kind: "configured-python"
    };
  }

  const pythonCandidates = [
    path.join(resourcesRoot, "python", "python.exe"),
    path.join(APP_ROOT, "python", "python.exe")
  ];
  for (const candidate of pythonCandidates) {
    if (fs.existsSync(candidate)) {
      return {
        command: candidate,
        args: backendUvicornArgs(settings),
        cwd: APP_ROOT,
        kind: "packaged-python"
      };
    }
  }

  return {
    command: configuredPython || "python",
    args: backendUvicornArgs(settings),
    cwd: APP_ROOT,
    kind: "system-python"
  };
}

function startBackend() {
  if (backendProcess && !backendProcess.killed) {
    return backendStatus();
  }
  const settings = readSettings();
  const backendCommand = resolveBackendCommand(settings);
  backendStopping = false;
  appendBackendLog(`\n[desktop] starting backend kind=${backendCommand.kind} command=${backendCommand.command} ${backendCommand.args.join(" ")}\n`, settings);
  appendBackendLog(
    `[desktop] appRoot=${APP_ROOT} storage=${resolveStoragePath(settings)} tavusEnabled=${Boolean(settings.TAVUS_ENABLED)} tavusReplica=${settings.TAVUS_REPLICA_ID || ""} tavusKeyConfigured=${Boolean(settings.TAVUS_API_KEY)} baiduXilingEnabled=${Boolean(settings.BAIDU_XILING_ENABLED)} baiduXilingFigure=${settings.BAIDU_XILING_FIGURE_ID || ""} hiflyEnabled=${Boolean(settings.HIFLY_ENABLED)} hiflyTokenConfigured=${Boolean(settings.HIFLY_TOKEN)}\n`,
    settings
  );
  backendProcess = spawn(backendCommand.command, backendCommand.args, {
    cwd: backendCommand.cwd,
    env: backendEnv(settings),
    windowsHide: true
  });
  backendProcess.stdout.on("data", (chunk) => appendBackendLog(chunk.toString(), settings));
  backendProcess.stderr.on("data", (chunk) => appendBackendLog(chunk.toString(), settings));
  backendProcess.on("error", (error) => {
    appendBackendLog(`[desktop] backend start error: ${error.message}\n`, settings);
    if (!backendStopping) {
      backendProcess = null;
    }
  });
  backendProcess.on("exit", (code, signal) => {
    appendBackendLog(`[桌面端] 后端已退出 code=${code} signal=${signal}\n`, settings);
    if (!backendStopping) {
      backendProcess = null;
    }
  });
  return backendStatus();
}

function stopBackend() {
  if (!backendProcess) return backendStatus();
  backendStopping = true;
  appendBackendLog("[桌面端] 正在停止后端\n");
  backendProcess.kill();
  backendProcess = null;
  backendStopping = false;
  return backendStatus();
}

function restartBackend() {
  stopBackend();
  return startBackend();
}

function waitForBackend(url, attempts = 60) {
  return new Promise((resolve, reject) => {
    let remaining = attempts;
    const tick = () => {
      const request = http.get(`${url}/health`, (response) => {
        response.resume();
        if (response.statusCode === 200) {
          resolve(true);
        } else if (--remaining <= 0) {
          reject(new Error(`backend health failed: ${response.statusCode}`));
        } else {
          setTimeout(tick, 500);
        }
      });
      request.on("error", () => {
        if (--remaining <= 0) {
          reject(new Error("backend did not become ready"));
        } else {
          setTimeout(tick, 500);
        }
      });
      request.setTimeout(1000, () => request.destroy());
    };
    tick();
  });
}

function desktopApiPayload(settings) {
  return {
    selected_preset: settings.selected_preset || "custom",
    tts_provider: settings.tts_provider || settings.TTS_ENGINE || "dryrun",
    digital_human_engine: settings.digital_human_engine || "auto",
    editing_output: settings.editing_output || "mp4_only",
    runtime_mode: settings.runtimeMode,
    STORAGE_DIR: settings.storagePath,
    PYTHON_PATH: settings.pythonPath,
    TTS_ENGINE: settings.TTS_ENGINE || "",
    TTS_BASE_URL: settings.TTS_BASE_URL || "",
    TTS_DEFAULT_VOICE: settings.TTS_DEFAULT_VOICE || "",
    COSYVOICE_URL: settings.COSYVOICE_URL || "",
    GPT_SOVITS_URL: settings.GPT_SOVITS_URL || "",
    PIXELLE_ENABLED: Boolean(settings.PIXELLE_ENABLED),
    PIXELLE_BASE_URL: settings.PIXELLE_BASE_URL || "",
    PIXELLE_SCRIPT_ENDPOINT: settings.PIXELLE_SCRIPT_ENDPOINT || "",
    PIXELLE_VIDEO_ENDPOINT: settings.PIXELLE_VIDEO_ENDPOINT || "",
    CLOUD_LIPSYNC_ENABLED: Boolean(settings.CLOUD_LIPSYNC_ENABLED),
    CLOUD_LIPSYNC_PROVIDER: settings.CLOUD_LIPSYNC_PROVIDER || "syncso",
    SYNCSO_BASE_URL: settings.SYNCSO_BASE_URL || "",
    SYNCSO_API_KEY: settings.SYNCSO_API_KEY || "",
    SYNCSO_MODEL: settings.SYNCSO_MODEL || "",
    SYNCSO_GENERATE_ENDPOINT: settings.SYNCSO_GENERATE_ENDPOINT || "",
    SYNCSO_TIMEOUT_SECONDS: Number(settings.SYNCSO_TIMEOUT_SECONDS || 1200),
    SYNCSO_POLL_INTERVAL_SECONDS: Number(settings.SYNCSO_POLL_INTERVAL_SECONDS || 5),
    OMNIHUMAN_ENABLED: Boolean(settings.OMNIHUMAN_ENABLED),
    OMNIHUMAN_ACCESS_KEY: settings.OMNIHUMAN_ACCESS_KEY || "",
    OMNIHUMAN_SECRET_KEY: settings.OMNIHUMAN_SECRET_KEY || "",
    OMNIHUMAN_ENDPOINT: settings.OMNIHUMAN_ENDPOINT || "",
    OMNIHUMAN_REGION: settings.OMNIHUMAN_REGION || "",
    OMNIHUMAN_SERVICE: settings.OMNIHUMAN_SERVICE || "",
    OMNIHUMAN_VERSION: settings.OMNIHUMAN_VERSION || "",
    OMNIHUMAN_REQ_KEY: settings.OMNIHUMAN_REQ_KEY || "",
    OMNIHUMAN_OUTPUT_RESOLUTION: Number(settings.OMNIHUMAN_OUTPUT_RESOLUTION || 1080),
    OMNIHUMAN_PROMPT: settings.OMNIHUMAN_PROMPT || "",
    OMNIHUMAN_PE_FAST_MODE: Boolean(settings.OMNIHUMAN_PE_FAST_MODE),
    OMNIHUMAN_TIMEOUT_SECONDS: Number(settings.OMNIHUMAN_TIMEOUT_SECONDS || 1200),
    OMNIHUMAN_POLL_INTERVAL_SECONDS: Number(settings.OMNIHUMAN_POLL_INTERVAL_SECONDS || 5),
    TAVUS_ENABLED: Boolean(settings.TAVUS_ENABLED),
    TAVUS_BASE_URL: settings.TAVUS_BASE_URL || "",
    TAVUS_API_KEY: settings.TAVUS_API_KEY || "",
    TAVUS_REPLICA_ID: settings.TAVUS_REPLICA_ID || "",
    TAVUS_VIDEO_ENDPOINT: settings.TAVUS_VIDEO_ENDPOINT || "",
    TAVUS_TIMEOUT_SECONDS: Number(settings.TAVUS_TIMEOUT_SECONDS || 1800),
    TAVUS_POLL_INTERVAL_SECONDS: Number(settings.TAVUS_POLL_INTERVAL_SECONDS || 8),
    BAIDU_XILING_ENABLED: Boolean(settings.BAIDU_XILING_ENABLED),
    BAIDU_XILING_BASE_URL: settings.BAIDU_XILING_BASE_URL || "https://open.xiling.baidu.com",
    BAIDU_XILING_APP_ID: settings.BAIDU_XILING_APP_ID || "",
    BAIDU_XILING_APP_KEY: settings.BAIDU_XILING_APP_KEY || "",
    BAIDU_XILING_FIGURE_ID: settings.BAIDU_XILING_FIGURE_ID || "",
    BAIDU_XILING_TTS_PERSON: settings.BAIDU_XILING_TTS_PERSON || "",
    BAIDU_XILING_WIDTH: Number(settings.BAIDU_XILING_WIDTH || 1080),
    BAIDU_XILING_HEIGHT: Number(settings.BAIDU_XILING_HEIGHT || 1920),
    BAIDU_XILING_TRANSPARENT: Boolean(settings.BAIDU_XILING_TRANSPARENT),
    BAIDU_XILING_TIMEOUT_SECONDS: Number(settings.BAIDU_XILING_TIMEOUT_SECONDS || 1200),
    BAIDU_XILING_POLL_INTERVAL_SECONDS: Number(settings.BAIDU_XILING_POLL_INTERVAL_SECONDS || 5),
    HIFLY_ENABLED: Boolean(settings.HIFLY_ENABLED),
    HIFLY_BASE_URL: settings.HIFLY_BASE_URL || "https://hfw-api.hifly.cc",
    HIFLY_TOKEN: settings.HIFLY_TOKEN || "",
    HIFLY_REQUIRED: Boolean(settings.HIFLY_REQUIRED),
    HIFLY_POLL_INTERVAL_SECONDS: Number(settings.HIFLY_POLL_INTERVAL_SECONDS || 5),
    HIFLY_TIMEOUT_SECONDS: Number(settings.HIFLY_TIMEOUT_SECONDS || 1800),
    CLOUD_VOICE_PROVIDER: settings.CLOUD_VOICE_PROVIDER || "edge_tts_no_clone",
    CLOUD_VIDEO_PROVIDER: settings.CLOUD_VIDEO_PROVIDER || "local",
    DASHSCOPE_API_KEY: settings.DASHSCOPE_API_KEY || "",
    ALIYUN_BAILIAN_REGION: settings.ALIYUN_BAILIAN_REGION || "cn-beijing",
    ALIYUN_VOICE_MODEL: settings.ALIYUN_VOICE_MODEL || "cosyvoice-v1",
    ELEVENLABS_API_KEY: settings.ELEVENLABS_API_KEY || "",
    AZURE_SPEECH_KEY: settings.AZURE_SPEECH_KEY || "",
    AZURE_SPEECH_ENDPOINT: settings.AZURE_SPEECH_ENDPOINT || "",
    CUSTOM_HTTP_TTS_BASE_URL: settings.CUSTOM_HTTP_TTS_BASE_URL || "",
    CUSTOM_HTTP_TTS_API_KEY: settings.CUSTOM_HTTP_TTS_API_KEY || "",
    FAL_API_KEY: settings.FAL_API_KEY || "",
    FAL_LATENTSYNC_MODEL: settings.FAL_LATENTSYNC_MODEL || "fal-ai/latentsync",
    FAL_MUSETALK_MODEL: settings.FAL_MUSETALK_MODEL || "fal-ai/musetalk",
    SELF_HOSTED_LIPSYNC_BASE_URL: settings.SELF_HOSTED_LIPSYNC_BASE_URL || "",
    SELF_HOSTED_LIPSYNC_API_KEY: settings.SELF_HOSTED_LIPSYNC_API_KEY || "",
    WAV2LIP_ENABLED: Boolean(settings.WAV2LIP_ENABLED),
    WAV2LIP_ROOT: settings.WAV2LIP_ROOT || "",
    WAV2LIP_CHECKPOINT: settings.WAV2LIP_CHECKPOINT || "",
    YY_WAV2LIP_ENABLED: Boolean(settings.YY_WAV2LIP_ENABLED),
    YY_WAV2LIP_CHECKPOINT: settings.YY_WAV2LIP_CHECKPOINT || "",
    YY_WAV2LIP_ROLE_MODEL_DIR: settings.YY_WAV2LIP_ROLE_MODEL_DIR || "",
    MUSETALK_ENABLED: Boolean(settings.MUSETALK_ENABLED),
    MUSETALK_ROOT: settings.MUSETALK_ROOT || "",
    MUSETALK_MODEL_DIR: settings.MUSETALK_MODEL_DIR || "",
    LATENTSYNC_ENABLED: Boolean(settings.LATENTSYNC_ENABLED),
    LATENTSYNC_ROOT: settings.LATENTSYNC_ROOT || "",
    LATENTSYNC_CHECKPOINT: settings.LATENTSYNC_CHECKPOINT || "",
    LATENTSYNC_UNET_CONFIG: settings.LATENTSYNC_UNET_CONFIG || "",
    JIANYING_ENABLED: Boolean(settings.JIANYING_ENABLED),
    JIANYING_DRAFT_ROOT: settings.JIANYING_DRAFT_ROOT || "",
    DUIX_ENABLED: Boolean(settings.DUIX_ENABLED),
    DUIX_BASE_URL: settings.DUIX_BASE_URL || ""
  };
}

function localSettingsFromApi(apiSettings) {
  return mergeSettings({
    ...apiSettings,
    runtimeMode: apiSettings.runtime_mode || apiSettings.runtimeMode,
    storagePath: apiSettings.STORAGE_DIR || apiSettings.storagePath,
    pythonPath: apiSettings.PYTHON_PATH || apiSettings.pythonPath,
    selected_preset: apiSettings.selected_preset || "custom",
    tts_provider: apiSettings.tts_provider || apiSettings.TTS_ENGINE || "dryrun",
    digital_human_engine: apiSettings.digital_human_engine || "auto",
    editing_output: apiSettings.editing_output || "mp4_only"
  });
}

function requestJson(settings, method, route, payload, timeoutMs = API_TIMEOUT_MS) {
  const body = payload === undefined ? "" : JSON.stringify(payload);
  const url = new URL(route, backendUrl(settings));
  return new Promise((resolve, reject) => {
    const req = http.request(
      url,
      {
        method,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body)
        },
        timeout: timeoutMs
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${method} ${route} failed: ${res.statusCode} ${text}`));
            return;
          }
          resolve(text ? JSON.parse(text) : {});
        });
      }
    );
    req.on("timeout", () => req.destroy(new Error(`${method} ${route} timed out`)));
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function requestText(settings, method, route, payload, timeoutMs = API_TIMEOUT_MS) {
  const body = payload === undefined ? "" : JSON.stringify(payload);
  const url = new URL(route, backendUrl(settings));
  return new Promise((resolve, reject) => {
    const req = http.request(
      url,
      {
        method,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body)
        },
        timeout: timeoutMs
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${method} ${route} failed: ${res.statusCode} ${text}`));
            return;
          }
          resolve(text);
        });
      }
    );
    req.on("timeout", () => req.destroy(new Error(`${method} ${route} timed out`)));
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function loadBackendFailurePage(error, settings = readSettings()) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>后端启动失败</title>
  <style>
    body { margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; background: #0f172a; color: #e5eefc; }
    .wrap { max-width: 860px; margin: 72px auto; padding: 32px; background: #111c33; border: 1px solid #2b3b5f; border-radius: 14px; }
    h1 { margin: 0 0 12px; font-size: 26px; }
    p { line-height: 1.7; color: #bdc9dd; }
    code { display: block; white-space: pre-wrap; word-break: break-all; background: #071022; border: 1px solid #26385c; border-radius: 8px; padding: 12px; color: #d8e7ff; }
    .hint { margin-top: 20px; padding: 14px; border-radius: 8px; background: #17345a; color: #dbeafe; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>后端启动失败</h1>
    <p>软件窗口已经打开，但本地服务没有启动成功，所以页面无法显示。请把下面的信息发给技术支持。</p>
    <p>错误原因</p>
    <code>${escapeHtml(error && error.message ? error.message : error)}</code>
    <p>后端地址</p>
    <code>${escapeHtml(backendUrl(settings))}</code>
    <p>程序目录</p>
    <code>${escapeHtml(APP_ROOT)}</code>
    <p>日志位置</p>
    <code>${escapeHtml(backendLogPath(settings))}</code>
    <div class="hint">如果这是客户电脑，通常表示安装包缺少随包后端运行文件，或被杀毒软件拦截。</div>
  </div>
</body>
</html>`;
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
}

async function callSimpleSettings(method, route, payload) {
  const settings = readSettings();
  startBackend();
  await waitForBackend(backendUrl(settings));
  return requestJson(settings, method, route, payload);
}

async function loadStudio() {
  const settings = readSettings();
  const url = backendUrl(settings);
  startBackend();
  try {
    await waitForBackend(url);
  } catch (error) {
    appendBackendLog(`[桌面端] 后端启动失败：${error.message}\n`, settings);
    loadBackendFailurePage(error, settings);
    return;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(url);
  }
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    title: "数字人智能体",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  loadStudio();
}

function createSettingsWindow() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus();
    return;
  }
  settingsWindow = new BrowserWindow({
    width: 980,
    height: 820,
    title: "数字人智能体设置",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  settingsWindow.on("closed", () => {
    settingsWindow = null;
  });
  settingsWindow.loadFile(path.join(__dirname, "settings.html"));
}

function createTray() {
  const icon = nativeImage.createFromDataURL(
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGklEQVR42mNkoBAwUqifYdQAhtEwCkbBBAAABV0AARd3E1sAAAAASUVORK5CYII="
  );
  tray = new Tray(icon);
  tray.setToolTip("数字人智能体");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "打开工作台", click: () => (mainWindow ? mainWindow.show() : createMainWindow()) },
      { label: "桌面版设置", click: createSettingsWindow },
      { label: "重启后端", click: restartBackend },
      { label: "停止后端", click: stopBackend },
      { label: "打开后端日志", click: () => shell.openPath(backendLogPath()) },
      { type: "separator" },
      { label: "退出", click: () => app.quit() }
    ])
  );
}

ipcMain.handle("desktop:get-settings", () => ({
  settings: readSettings(),
  backend: backendStatus()
}));
ipcMain.handle("desktop:save-settings", (_event, payload) => ({
  settings: saveSettings(payload),
  backend: backendStatus()
}));
ipcMain.handle("desktop:validate-settings", async (_event, payload) => {
  const settings = saveSettings(payload || {});
  startBackend();
  await waitForBackend(backendUrl(settings));
  const apiPayload = desktopApiPayload(settings);
  await requestJson(settings, "PUT", "/settings/desktop", apiPayload);
  return requestJson(settings, "POST", "/settings/desktop/validate", apiPayload);
});
ipcMain.handle("desktop:get-alignment-report", async (_event, payload) => {
  const settings = saveSettings(payload || readSettings());
  startBackend();
  await waitForBackend(backendUrl(settings));
  await requestJson(settings, "PUT", "/settings/desktop", desktopApiPayload(settings));
  return requestJson(settings, "GET", "/settings/alignment-report");
});
ipcMain.handle("desktop:simple-settings", async () => {
  const body = await callSimpleSettings("GET", "/settings/simple");
  if (body.advanced_config) saveSettings(localSettingsFromApi(body.advanced_config));
  return body;
});
ipcMain.handle("desktop:apply-settings-preset", async (_event, payload) => {
  const body = await callSimpleSettings("POST", "/settings/simple/apply-preset", payload || {});
  if (body.advanced_config) saveSettings(localSettingsFromApi(body.advanced_config));
  return body;
});
ipcMain.handle("desktop:autodetect-settings", async () => callSimpleSettings("POST", "/settings/simple/autodetect"));
ipcMain.handle("desktop:validate-simple-settings", async (_event, payload) => {
  const settings = saveSettings(payload || readSettings());
  startBackend();
  await waitForBackend(backendUrl(settings));
  return requestJson(settings, "POST", "/settings/simple/validate", desktopApiPayload(settings));
});
ipcMain.handle("desktop:copy-env", async (_event, payload) => {
  const settings = saveSettings(payload || readSettings());
  startBackend();
  await waitForBackend(backendUrl(settings));
  return requestText(settings, "POST", "/settings/simple/copy-env", desktopApiPayload(settings));
});
ipcMain.handle("desktop:cloud-cost-estimate", async (_event, payload) => {
  const settings = saveSettings((payload && payload.settings) || readSettings());
  startBackend();
  await waitForBackend(backendUrl(settings));
  const params = new URLSearchParams({
    videos_per_month: String(payload?.videos_per_month || 30),
    average_duration_seconds: String(payload?.average_duration_seconds || 60),
    average_chinese_chars_per_video: String(payload?.average_chinese_chars_per_video || 500),
    voice_provider: payload?.voice_provider || settings.CLOUD_VOICE_PROVIDER || "aliyun_bailian_cosyvoice",
    video_provider: payload?.video_provider || settings.CLOUD_VIDEO_PROVIDER || "fal_latentsync"
  });
  return requestJson(settings, "GET", `/settings/cloud-cost-estimate?${params.toString()}`);
});
ipcMain.handle("desktop:simple-alignment-report", async () => callSimpleSettings("GET", "/settings/simple/alignment-report"));
ipcMain.handle("desktop:restart-backend", () => restartBackend());
ipcMain.handle("desktop:stop-backend", () => stopBackend());
ipcMain.handle("desktop:start-backend", () => startBackend());
ipcMain.handle("desktop:get-logs", () => {
  const logPath = backendLogPath();
  return fs.existsSync(logPath) ? fs.readFileSync(logPath, "utf8").slice(-60000) : "";
});
ipcMain.handle("desktop:open-studio", async () => {
  await loadStudio();
  if (mainWindow) mainWindow.show();
  return backendStatus();
});
ipcMain.handle("desktop:open-external-url", async (_event, url) => {
  const allowed = new Set(["https://platform.tavus.io/", "https://docs.tavus.io/"]);
  if (!allowed.has(url)) {
    throw new Error(`不允许打开的外部链接：${url}`);
  }
  await shell.openExternal(url);
  return { opened: true, url };
});

app.whenReady().then(() => {
  createMainWindow();
  createTray();
});

app.on("window-all-closed", (event) => {
  event.preventDefault();
  if (mainWindow) mainWindow.hide();
});

app.on("before-quit", () => {
  stopBackend();
});
