const runtimeFields = ["runtimeMode", "storagePath", "pythonPath", "backendHost", "backendPort"];
const simpleFields = ["ttsProvider", "digitalHumanEngine", "editingOutput"];
const textFields = [
  "TTS_ENGINE",
  "TTS_BASE_URL",
  "TTS_DEFAULT_VOICE",
  "COSYVOICE_URL",
  "GPT_SOVITS_URL",
  "PIXELLE_BASE_URL",
  "PIXELLE_SCRIPT_ENDPOINT",
  "PIXELLE_VIDEO_ENDPOINT",
  "CLOUD_LIPSYNC_PROVIDER",
  "SYNCSO_BASE_URL",
  "SYNCSO_API_KEY",
  "SYNCSO_MODEL",
  "SYNCSO_GENERATE_ENDPOINT",
  "SYNCSO_TIMEOUT_SECONDS",
  "SYNCSO_POLL_INTERVAL_SECONDS",
  "OMNIHUMAN_ACCESS_KEY",
  "OMNIHUMAN_SECRET_KEY",
  "OMNIHUMAN_ENDPOINT",
  "OMNIHUMAN_REGION",
  "OMNIHUMAN_SERVICE",
  "OMNIHUMAN_VERSION",
  "OMNIHUMAN_REQ_KEY",
  "OMNIHUMAN_OUTPUT_RESOLUTION",
  "OMNIHUMAN_PROMPT",
  "OMNIHUMAN_TIMEOUT_SECONDS",
  "OMNIHUMAN_POLL_INTERVAL_SECONDS",
  "TAVUS_BASE_URL",
  "TAVUS_API_KEY",
  "TAVUS_REPLICA_ID",
  "TAVUS_VIDEO_ENDPOINT",
  "TAVUS_TIMEOUT_SECONDS",
  "TAVUS_POLL_INTERVAL_SECONDS",
  "BAIDU_XILING_BASE_URL",
  "BAIDU_XILING_APP_ID",
  "BAIDU_XILING_APP_KEY",
  "BAIDU_XILING_FIGURE_ID",
  "BAIDU_XILING_TTS_PERSON",
  "BAIDU_XILING_WIDTH",
  "BAIDU_XILING_HEIGHT",
  "BAIDU_XILING_TIMEOUT_SECONDS",
  "BAIDU_XILING_POLL_INTERVAL_SECONDS",
  "HIFLY_BASE_URL",
  "HIFLY_TOKEN",
  "HIFLY_POLL_INTERVAL_SECONDS",
  "HIFLY_TIMEOUT_SECONDS",
  "CLOUD_VOICE_PROVIDER",
  "CLOUD_VIDEO_PROVIDER",
  "DASHSCOPE_API_KEY",
  "ALIYUN_BAILIAN_REGION",
  "ALIYUN_VOICE_MODEL",
  "ELEVENLABS_API_KEY",
  "AZURE_SPEECH_KEY",
  "AZURE_SPEECH_ENDPOINT",
  "CUSTOM_HTTP_TTS_BASE_URL",
  "CUSTOM_HTTP_TTS_API_KEY",
  "FAL_API_KEY",
  "FAL_LATENTSYNC_MODEL",
  "FAL_MUSETALK_MODEL",
  "SELF_HOSTED_LIPSYNC_BASE_URL",
  "SELF_HOSTED_LIPSYNC_API_KEY",
  "WAV2LIP_ROOT",
  "WAV2LIP_CHECKPOINT",
  "YY_WAV2LIP_CHECKPOINT",
  "YY_WAV2LIP_ROLE_MODEL_DIR",
  "MUSETALK_ROOT",
  "MUSETALK_MODEL_DIR",
  "LATENTSYNC_ROOT",
  "LATENTSYNC_CHECKPOINT",
  "LATENTSYNC_UNET_CONFIG",
  "JIANYING_DRAFT_ROOT",
  "DUIX_BASE_URL"
];
const checkboxFields = [
  "PIXELLE_ENABLED",
  "CLOUD_LIPSYNC_ENABLED",
  "OMNIHUMAN_ENABLED",
  "OMNIHUMAN_PE_FAST_MODE",
  "TAVUS_ENABLED",
  "BAIDU_XILING_ENABLED",
  "BAIDU_XILING_TRANSPARENT",
  "HIFLY_ENABLED",
  "HIFLY_REQUIRED",
  "WAV2LIP_ENABLED",
  "YY_WAV2LIP_ENABLED",
  "MUSETALK_ENABLED",
  "LATENTSYNC_ENABLED",
  "JIANYING_ENABLED",
  "DUIX_ENABLED"
];
const hiddenSecretFields = new Set([
  "SYNCSO_API_KEY",
  "PIXVERSE_API_KEY",
  "OMNIHUMAN_ACCESS_KEY",
  "OMNIHUMAN_SECRET_KEY",
  "TAVUS_API_KEY",
  "BAIDU_XILING_APP_ID",
  "BAIDU_XILING_APP_KEY",
  "HIFLY_TOKEN",
  "DASHSCOPE_API_KEY",
  "ELEVENLABS_API_KEY",
  "AZURE_SPEECH_KEY",
  "CUSTOM_HTTP_TTS_API_KEY",
  "FAL_API_KEY",
  "SELF_HOSTED_LIPSYNC_API_KEY",
  "OBJECT_STORAGE_ACCESS_KEY_ID",
  "OBJECT_STORAGE_SECRET_ACCESS_KEY"
]);
const presetLabels = {
  dryrun_trial: "试用流程",
  yuanyue_compat: "对齐元岳/AivoClaw路线",
  high_quality: "高质量数字人",
  batch_production: "批量生产",
  custom: "自定义"
};
// 校验项中文名：raw 环境变量仍保留在高级设置里，普通结果默认显示中文。
const checkLabels = {
  dry_run_available: "试用模式可用",
  TTS_ENGINE: "声音方案",
  TTS_BASE_URL: "语音服务地址",
  COSYVOICE_URL: "CosyVoice 服务地址",
  GPT_SOVITS_URL: "GPT-SoVITS 服务地址",
  PIXELLE_BASE_URL: "Pixelle 后端地址",
  CLOUD_LIPSYNC_ENABLED: "Sync.so 云端口型同步",
  CLOUD_LIPSYNC_PROVIDER: "云端口型同步服务",
  SYNCSO_BASE_URL: "Sync.so 服务地址",
  SYNCSO_API_KEY: "Sync.so API Key",
  SYNCSO_MODEL: "Sync.so 模型",
  TAVUS_ENABLED: "Tavus 云端数字人",
  TAVUS_BASE_URL: "Tavus 服务地址",
  TAVUS_API_KEY: "Tavus API Key",
  TAVUS_REPLICA_ID: "Tavus Replica ID",
  BAIDU_XILING_ENABLED: "百度曦灵数字人",
  BAIDU_XILING_BASE_URL: "百度曦灵服务地址",
  BAIDU_XILING_APP_ID: "百度曦灵 AppID",
  BAIDU_XILING_APP_KEY: "百度曦灵 AppKey",
  BAIDU_XILING_FIGURE_ID: "百度曦灵数字人形象 ID",
  BAIDU_XILING_TTS_PERSON: "百度曦灵发音人 ID",
  BAIDU_XILING_WIDTH: "百度曦灵视频宽度",
  BAIDU_XILING_HEIGHT: "百度曦灵视频高度",
  BAIDU_XILING_TRANSPARENT: "百度曦灵透明背景",
  BAIDU_XILING_TIMEOUT_SECONDS: "百度曦灵超时时间",
  BAIDU_XILING_POLL_INTERVAL_SECONDS: "百度曦灵轮询间隔",
  HIFLY_ENABLED: "飞影 API 数字人",
  HIFLY_BASE_URL: "飞影 API 地址",
  HIFLY_TOKEN: "飞影 API Token",
  HIFLY_REQUIRED: "飞影真实模式必需",
  HIFLY_POLL_INTERVAL_SECONDS: "飞影轮询间隔",
  HIFLY_TIMEOUT_SECONDS: "飞影超时时间",
  DUIX_BASE_URL: "Duix HTTP 地址",
  WAV2LIP_ROOT: "Wav2Lip 源码目录",
  WAV2LIP_CHECKPOINT: "Wav2Lip 模型文件",
  YY_WAV2LIP_CHECKPOINT: "YYWav2Lip 模型文件",
  YY_WAV2LIP_ROLE_MODEL_DIR: "YY 角色模型目录",
  MUSETALK_ROOT: "MuseTalk 源码目录",
  MUSETALK_MODEL_DIR: "MuseTalk 模型目录",
  LATENTSYNC_ROOT: "LatentSync 源码目录",
  LATENTSYNC_CHECKPOINT: "LatentSync 模型文件",
  LATENTSYNC_UNET_CONFIG: "LatentSync 配置文件",
  JIANYING_DRAFT_ROOT: "剪映草稿目录",
  repository_model_weight_policy: "模型权重提交检查"
};
Object.assign(checkLabels, {
  CLOUD_VOICE_PROVIDER: "云端声音服务",
  CLOUD_VIDEO_PROVIDER: "云端视频/口型同步服务",
  DASHSCOPE_API_KEY: "阿里云百炼 API Key",
  ALIYUN_BAILIAN_REGION: "阿里云百炼区域",
  ALIYUN_VOICE_MODEL: "阿里云声音模型",
  ELEVENLABS_API_KEY: "ElevenLabs API Key",
  AZURE_SPEECH_KEY: "Azure Speech Key",
  AZURE_SPEECH_ENDPOINT: "Azure 语音服务地址",
  CUSTOM_HTTP_TTS_BASE_URL: "自定义 TTS 地址",
  CUSTOM_HTTP_TTS_API_KEY: "自定义 TTS API Key",
  FAL_API_KEY: "fal.ai API Key",
  FAL_LATENTSYNC_MODEL: "fal.ai LatentSync 模型",
  FAL_MUSETALK_MODEL: "fal.ai MuseTalk 模型",
  SELF_HOSTED_LIPSYNC_BASE_URL: "自建口型同步地址",
  SELF_HOSTED_LIPSYNC_API_KEY: "自建口型同步 API Key",
  aliyun_bailian_cosyvoice: "阿里云百炼 CosyVoice 声音克隆",
  aliyun_bailian_qwen_tts: "阿里云百炼 Qwen-TTS",
  aliyun_bailian_minimax: "阿里云百炼 MiniMax 声音克隆",
  fal_latentsync: "fal.ai LatentSync 云端渲染",
  fal_musetalk: "fal.ai MuseTalk 云端预览",
  self_hosted_lipsync: "自建口型同步服务",
  baidu_xiling: "百度曦灵数字人",
  baidu_xiling_cloud: "百度曦灵数字人",
  hifly: "飞影 API 数字人",
  hifly_cloud: "飞影 API 数字人"
});
const checkStatusLabels = {
  green: "可用",
  yellow: "注意",
  red: "缺失",
  ready: "可用",
  warning: "注意",
  missing: "缺失",
  disabled: "未启用"
};
let selectedPreset = "custom";
const actionButtonIds = [
  "autoDetectBtn",
  "applyRecommendedBtn",
  "saveSettingsBtn",
  "validateSettingsBtn",
  "copyEnvBtn",
  "alignmentReportBtn",
  "restartBackendBtn",
  "stopBackendBtn",
  "openStudioBtn",
  "refreshLogBtn",
  "openTavusConsoleBtn",
  "openTavusDocsBtn",
  "copyTavusReplicaBtn",
  "estimateCloudCostBtn"
];

const $ = (id) => document.getElementById(id);

function hideSecretFields() {
  for (const id of hiddenSecretFields) {
    const input = $(id);
    const label = input ? input.closest("label") : null;
    if (label) label.style.display = "none";
  }
}

function setStatus(backend) {
  const status = backend && backend.running ? `运行中 pid=${backend.pid}` : "已停止";
  const mode = backend && backend.runtimeMode ? backend.runtimeMode : "standard";
  $("backendStatus").textContent = `${status} / ${mode} / ${backend ? backend.url : ""}`;
}

function fill(settings) {
  hideSecretFields();
  const mode = settings.runtimeMode || settings.runtime_mode || (settings.dryRun ? "dry-run" : "standard");
  selectedPreset = settings.selected_preset || selectedPreset || "custom";
  $("runtimeMode").value = mode;
  $("ttsProvider").value = settings.tts_provider || settings.TTS_ENGINE || "dryrun";
  $("digitalHumanEngine").value = settings.digital_human_engine || "auto";
  $("editingOutput").value = settings.editing_output || "mp4_only";
  $("storagePath").value = settings.storagePath || settings.STORAGE_DIR || "storage";
  $("pythonPath").value = settings.pythonPath || settings.PYTHON_PATH || "python";
  $("backendHost").value = settings.backendHost || "127.0.0.1";
  $("backendPort").value = settings.backendPort || 8080;

  for (const id of textFields) {
    if ($(id)) $(id).value = settings[id] ?? defaultTextValue(id);
  }
  for (const id of checkboxFields) {
    if ($(id)) $(id).checked = Boolean(settings[id]);
  }
  syncMirrorFields();
  syncSimpleChoicesToAdvanced(false);
  highlightPreset();
  $("envOutput").textContent = toEnvOutput(collect());
}

function syncMirrorFields() {
  for (const mirror of document.querySelectorAll("[data-mirror-for]")) {
    const source = $(mirror.dataset.mirrorFor);
    if (source) mirror.value = source.value || "";
  }
}

function fillAdvanced(config) {
  fill({
    ...config,
    runtimeMode: config.runtime_mode,
    storagePath: config.STORAGE_DIR,
    pythonPath: config.PYTHON_PATH
  });
}

function defaultTextValue(id) {
  const defaults = {
    TTS_ENGINE: "dryrun",
    PIXELLE_BASE_URL: "http://127.0.0.1:8000",
    PIXELLE_SCRIPT_ENDPOINT: "/api/content/narration",
    PIXELLE_VIDEO_ENDPOINT: "/api/video/generate/sync",
    CLOUD_LIPSYNC_PROVIDER: "syncso",
    SYNCSO_BASE_URL: "https://api.sync.so",
    SYNCSO_MODEL: "lipsync-2",
    SYNCSO_GENERATE_ENDPOINT: "/v2/generate",
    SYNCSO_TIMEOUT_SECONDS: "1200",
    SYNCSO_POLL_INTERVAL_SECONDS: "5",
    OMNIHUMAN_ENDPOINT: "https://visual.volcengineapi.com",
    OMNIHUMAN_REGION: "cn-north-1",
    OMNIHUMAN_SERVICE: "cv",
    OMNIHUMAN_VERSION: "2024-06-06",
    OMNIHUMAN_REQ_KEY: "jimeng_realman_avatar_picture_omni_v15",
    OMNIHUMAN_OUTPUT_RESOLUTION: "1080",
    OMNIHUMAN_PROMPT: "自然口播，面带微笑，保持人物身份一致。",
    OMNIHUMAN_TIMEOUT_SECONDS: "1200",
    OMNIHUMAN_POLL_INTERVAL_SECONDS: "5",
    TAVUS_BASE_URL: "https://tavusapi.com",
    TAVUS_REPLICA_ID: "r9d30b0e55ac",
    TAVUS_VIDEO_ENDPOINT: "/v2/videos",
    TAVUS_TIMEOUT_SECONDS: "1800",
    TAVUS_POLL_INTERVAL_SECONDS: "8",
    BAIDU_XILING_BASE_URL: "https://open.xiling.baidu.com",
    BAIDU_XILING_WIDTH: "1080",
    BAIDU_XILING_HEIGHT: "1920",
    BAIDU_XILING_TIMEOUT_SECONDS: "1200",
    BAIDU_XILING_POLL_INTERVAL_SECONDS: "5",
    HIFLY_BASE_URL: "https://hfw-api.hifly.cc",
    HIFLY_POLL_INTERVAL_SECONDS: "5",
    HIFLY_TIMEOUT_SECONDS: "1800",
    CLOUD_VOICE_PROVIDER: "edge_tts_no_clone",
    CLOUD_VIDEO_PROVIDER: "local",
    ALIYUN_BAILIAN_REGION: "cn-beijing",
    ALIYUN_VOICE_MODEL: "cosyvoice-v1",
    FAL_LATENTSYNC_MODEL: "fal-ai/latentsync",
    FAL_MUSETALK_MODEL: "fal-ai/musetalk",
    WAV2LIP_ROOT: "third_party/Wav2Lip",
    WAV2LIP_CHECKPOINT: "checkpoints/wav2lip.pth",
    YY_WAV2LIP_CHECKPOINT: "resource/checkpoints/yywav2lip.pth",
    MUSETALK_ROOT: "third_party/MuseTalk",
    LATENTSYNC_ROOT: "third_party/LatentSync",
    DUIX_BASE_URL: "http://127.0.0.1:8383"
  };
  return defaults[id] || "";
}

function collect() {
  syncSimpleChoicesToAdvanced(false);
  const runtimeMode = $("runtimeMode").value || "standard";
  const settings = {
    selected_preset: selectedPreset,
    tts_provider: $("ttsProvider").value,
    digital_human_engine: $("digitalHumanEngine").value,
    editing_output: $("editingOutput").value,
    runtimeMode,
    runtime_mode: runtimeMode,
    dryRun: runtimeMode === "dry-run",
    storagePath: $("storagePath").value.trim() || "storage",
    pythonPath: $("pythonPath").value.trim() || "python",
    backendHost: $("backendHost").value.trim() || "127.0.0.1",
    backendPort: Number($("backendPort").value || 8080),
    STORAGE_DIR: $("storagePath").value.trim() || "storage",
    PYTHON_PATH: $("pythonPath").value.trim() || "python"
  };
  for (const id of textFields) {
    if ($(id)) settings[id] = $(id).value.trim();
  }
  for (const id of checkboxFields) {
    settings[id] = $(id).checked;
  }
  return settings;
}

function syncSimpleChoicesToAdvanced(forceEngineToggle = true) {
  const provider = $("ttsProvider").value || "dryrun";
  $("TTS_ENGINE").value = provider;
  if (provider === "cosyvoice_http" && !$("TTS_BASE_URL").value.trim()) {
    $("TTS_BASE_URL").value = $("COSYVOICE_URL").value.trim() || "http://127.0.0.1:50000";
  }
  if (provider === "gpt_sovits_http" && !$("TTS_BASE_URL").value.trim()) {
    $("TTS_BASE_URL").value = $("GPT_SOVITS_URL").value.trim() || "http://127.0.0.1:9880";
  }
  if (provider === "aliyun_tts") {
    $("TTS_ENGINE").value = "cloud_clone";
    $("CLOUD_VOICE_PROVIDER").value = "aliyun_bailian_cosyvoice";
  }

  if (!forceEngineToggle) return;
  const engine = $("digitalHumanEngine").value;
  if (engine === "static") {
    setEngineEnabled(false, false, false, false, false, false, false, false);
  } else if (engine === "syncso") {
    setEngineEnabled(false, false, false, false, false, true, false, false);
  } else if (engine === "omnihuman") {
    setEngineEnabled(false, false, false, false, false, false, true, false);
  } else if (engine === "tavus") {
    setEngineEnabled(false, false, false, false, false, false, false, true);
  } else if (engine === "baidu_xiling") {
    setEngineEnabled(false, false, false, false, false, false, false, false, true);
    $("CLOUD_VIDEO_PROVIDER").value = "baidu_xiling";
  } else if (engine === "hifly") {
    setEngineEnabled(false, false, false, false, false, false, false, false, false, true);
    $("CLOUD_VIDEO_PROVIDER").value = "hifly";
  } else if (engine === "yywav2lip") {
    setEngineEnabled(true, true, false, false, false, false, false, false);
  } else if (engine === "wav2lip") {
    setEngineEnabled(true, false, false, false, false, false, false, false);
  } else if (engine === "musetalk") {
    setEngineEnabled(false, false, true, false, false, false, false, false);
  } else if (engine === "latentsync") {
    setEngineEnabled(false, false, true, true, false, false, false, false);
    if ($("CLOUD_VIDEO_PROVIDER").value === "local") $("CLOUD_VIDEO_PROVIDER").value = "fal_latentsync";
  } else if (engine === "duix_http") {
    setEngineEnabled(false, false, false, false, true, false, false, false);
  }
  $("JIANYING_ENABLED").checked = $("editingOutput").value !== "mp4_only";
  syncMirrorFields();
}

function setEngineEnabled(wav2lip, yywav2lip, musetalk, latentsync, duix, cloudLipsync, omnihuman = false, tavus = false, baiduXiling = false, hifly = false) {
  $("WAV2LIP_ENABLED").checked = wav2lip;
  $("YY_WAV2LIP_ENABLED").checked = yywav2lip;
  $("MUSETALK_ENABLED").checked = musetalk;
  $("LATENTSYNC_ENABLED").checked = latentsync;
  $("DUIX_ENABLED").checked = duix;
  $("CLOUD_LIPSYNC_ENABLED").checked = cloudLipsync;
  $("OMNIHUMAN_ENABLED").checked = omnihuman;
  $("TAVUS_ENABLED").checked = tavus;
  $("BAIDU_XILING_ENABLED").checked = baiduXiling;
  $("HIFLY_ENABLED").checked = hifly;
  if (cloudLipsync) {
    $("CLOUD_LIPSYNC_PROVIDER").value = "syncso";
    if (!$("SYNCSO_BASE_URL").value.trim()) $("SYNCSO_BASE_URL").value = "https://api.sync.so";
    if (!$("SYNCSO_MODEL").value.trim()) $("SYNCSO_MODEL").value = "lipsync-2";
    if (!$("SYNCSO_GENERATE_ENDPOINT").value.trim()) $("SYNCSO_GENERATE_ENDPOINT").value = "/v2/generate";
  }
  if (tavus) {
    if (!$("TAVUS_BASE_URL").value.trim()) $("TAVUS_BASE_URL").value = "https://tavusapi.com";
    if (!$("TAVUS_REPLICA_ID").value.trim()) $("TAVUS_REPLICA_ID").value = "r9d30b0e55ac";
    if (!$("TAVUS_VIDEO_ENDPOINT").value.trim()) $("TAVUS_VIDEO_ENDPOINT").value = "/v2/videos";
  }
  if (baiduXiling) {
    if (!$("BAIDU_XILING_BASE_URL").value.trim()) $("BAIDU_XILING_BASE_URL").value = "https://open.xiling.baidu.com";
    if (!$("BAIDU_XILING_WIDTH").value.trim()) $("BAIDU_XILING_WIDTH").value = "1080";
    if (!$("BAIDU_XILING_HEIGHT").value.trim()) $("BAIDU_XILING_HEIGHT").value = "1920";
  }
  if (hifly) {
    if (!$("HIFLY_BASE_URL").value.trim()) $("HIFLY_BASE_URL").value = "https://hfw-api.hifly.cc";
  }
}

function toEnvOutput(settings) {
  const lines = [
    `RUNTIME_MODE=${settings.runtimeMode}`,
    `DRY_RUN=${settings.runtimeMode === "dry-run" ? "true" : "false"}`,
    `STORAGE_DIR=${settings.storagePath}`,
    `PYTHON_PATH=${settings.pythonPath}`
  ];
  for (const id of [...textFields, ...checkboxFields]) {
    const value = typeof settings[id] === "boolean" ? (settings[id] ? "true" : "false") : settings[id] || "";
    lines.push(`${id}=${value}`);
  }
  return lines.join("\n") + "\n";
}

async function load() {
  const body = await window.aivoDesktop.getSettings();
  fill(body.settings);
  setStatus(body.backend);
  await refreshLogs();
  try {
    const simple = await window.aivoDesktop.getSimpleSettings();
    renderSimpleSettings(simple);
  } catch (error) {
    $("validationSummary").className = "status-line status-yellow";
    $("validationSummary").textContent = `后端设置向导暂不可用：${error.message || String(error)}`;
  }
}

function renderSimpleSettings(body) {
  if (body.advanced_config) fillAdvanced(body.advanced_config);
  selectedPreset = body.selected_preset || selectedPreset;
  highlightPreset();
  renderModuleStatuses(body.module_statuses || []);
  if (body.env_output) $("envOutput").textContent = body.env_output;
  if (body.recommended_actions && body.recommended_actions.length) {
    $("validationSummary").className = "status-line status-yellow";
    $("validationSummary").textContent = body.recommended_actions[0];
  }
}

function renderModuleStatuses(statuses) {
  const grid = $("moduleStatusCards");
  grid.innerHTML = "";
  for (const status of statuses) {
    const card = document.createElement("div");
    card.className = `status-card ${status.status || "disabled"}`;
    const title = document.createElement("h3");
    const label = document.createElement("span");
    label.textContent = status.label || status.key;
    const badge = document.createElement("span");
    badge.className = `badge ${status.status || "disabled"}`;
    badge.textContent = statusText(status.status);
    title.appendChild(label);
    title.appendChild(badge);
    const message = document.createElement("p");
    message.textContent = status.message || "";
    const action = document.createElement("button");
    action.type = "button";
    action.textContent = "配置/检测";
    action.onclick = () => openAdvancedFor(status.key);
    card.appendChild(title);
    card.appendChild(message);
    card.appendChild(action);
    grid.appendChild(card);
  }
}

function statusText(status) {
  return {
    ready: "可用",
    warning: "注意",
    missing: "缺失",
    disabled: "未启用"
  }[status] || "未知";
}

function openAdvancedFor(key) {
  $("advancedSettings").open = true;
  const focusMap = {
    tts: "TTS_ENGINE",
    pixelle: "PIXELLE_BASE_URL",
    cloud_lipsync: "SYNCSO_API_KEY",
    cloud_voice: "DASHSCOPE_API_KEY",
    cloud_video: "FAL_API_KEY",
    aliyun_bailian_cosyvoice: "DASHSCOPE_API_KEY",
    aliyun_bailian_qwen_tts: "DASHSCOPE_API_KEY",
    aliyun_bailian_minimax: "DASHSCOPE_API_KEY",
    fal_latentsync: "FAL_API_KEY",
    fal_musetalk: "FAL_API_KEY",
    self_hosted_lipsync: "SELF_HOSTED_LIPSYNC_BASE_URL",
    omnihuman_cloud: "OMNIHUMAN_ACCESS_KEY",
    tavus_cloud: "TAVUS_REPLICA_ID",
    baidu_xiling: "BAIDU_XILING_APP_ID",
    baidu_xiling_cloud: "BAIDU_XILING_APP_ID",
    hifly: "HIFLY_TOKEN",
    hifly_cloud: "HIFLY_TOKEN",
    wav2lip: "WAV2LIP_CHECKPOINT",
    yywav2lip: "YY_WAV2LIP_ROLE_MODEL_DIR",
    musetalk: "MUSETALK_MODEL_DIR",
    latentsync: "LATENTSYNC_CHECKPOINT",
    jianying: "JIANYING_DRAFT_ROOT",
    duix: "DUIX_BASE_URL"
  };
  const target = $(focusMap[key]);
  if (target) target.focus();
}

async function autoDetectSettings() {
  setActionStatus("正在自动检测本机服务、模型文件和剪映目录...", "yellow");
  const body = await window.aivoDesktop.autoDetectSettings();
  renderModuleStatuses(body.module_statuses || []);
  $("validationSummary").className = "status-line status-yellow";
  $("validationSummary").textContent = (body.recommended_actions && body.recommended_actions[0]) || "自动检测完成。";
}

async function applyRecommendedConfig() {
  setActionStatus("正在应用推荐配置，可能需要 10-30 秒...", "yellow");
  const presetId = selectedPreset || "dryrun_trial";
  const body = await window.aivoDesktop.applySettingsPreset({ preset_id: presetId, auto_detect: true });
  renderSimpleSettings(body);
  const status = $("validationSummary");
  status.className = "status-line status-green";
  status.textContent = `已应用：${presetLabels[presetId] || presetId}`;
}

async function saveSettings() {
  setActionStatus("正在保存设置...", "yellow");
  const settings = collect();
  const body = await window.aivoDesktop.saveSettings(settings);
  fill(body.settings);
  setStatus(body.backend);
  $("envOutput").textContent = toEnvOutput(settings);
  const status = $("validationSummary");
  status.className = "status-line status-green";
  status.textContent = "设置已保存。";
}

function renderValidation(validation) {
  const summary = $("validationSummary");
  const status = validation.overall_status || "yellow";
  summary.className = `status-line status-${status}`;
  summary.textContent = `校验结果：${checkStatusText(status)}`;
  $("envOutput").textContent = validation.env_output || toEnvOutput(collect());
  renderModuleStatuses(validation.module_statuses || []);

  const list = $("validationResults");
  list.innerHTML = "";
  for (const check of validation.checks || []) {
    const item = document.createElement("div");
    item.className = `check-item ${check.status || "yellow"}`;
    const title = document.createElement("strong");
    title.textContent = `${checkNameText(check.name)} / ${checkStatusText(check.status)}`;
    const message = document.createElement("span");
    message.textContent = localizeCheckMessage(check.message || "");
    item.appendChild(title);
    item.appendChild(message);
    list.appendChild(item);
  }
}

function checkNameText(name) {
  return checkLabels[name] || name || "校验项";
}

function checkStatusText(status) {
  return checkStatusLabels[status] || status || "未知";
}

function localizeCheckMessage(message) {
  return message
    .replace(/^GET (.+) returned (\d+)\.$/, "访问 $1 返回状态码 $2。")
    .replace(/^URL not reachable: (.+); (.+)$/, "服务地址不可访问：$1；$2")
    .replace(/^file exists: (.+)$/, "文件存在：$1")
    .replace(/^file missing: (.+)$/, "文件不存在：$1")
    .replace(/^dir exists: (.+)$/, "目录存在：$1")
    .replace(/^dir missing: (.+)$/, "目录不存在：$1");
}

async function validateSettings() {
  setActionStatus("正在校验当前配置...", "yellow");
  const settings = collect();
  const validation = window.aivoDesktop.validateSimpleSettings
    ? await window.aivoDesktop.validateSimpleSettings(settings)
    : await window.aivoDesktop.validateSettings(settings);
  renderValidation(validation);
  const report = window.aivoDesktop.getSimpleAlignmentReport
    ? await window.aivoDesktop.getSimpleAlignmentReport()
    : await window.aivoDesktop.getAlignmentReport(settings);
  $("alignmentReport").textContent = JSON.stringify(report, null, 2);
}

async function copyEnvOutput() {
  setActionStatus("正在生成 .env...", "yellow");
  const text = window.aivoDesktop.copyEnv
    ? await window.aivoDesktop.copyEnv(collect())
    : $("envOutput").textContent || toEnvOutput(collect());
  $("envOutput").textContent = text;
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    // The desktop shell may block clipboard access on some Windows policies; still show the text.
  }
  const summary = $("validationSummary");
  summary.className = "status-line status-green";
  summary.textContent = ".env 已生成，可复制使用。";
}

async function estimateCloudCost() {
  setActionStatus("正在估算云端成本...", "yellow");
  const settings = collect();
  const payload = {
    settings,
    videos_per_month: Number($("costVideosPerMonth")?.value || 30),
    average_duration_seconds: Number($("costAverageDurationSeconds")?.value || 60),
    average_chinese_chars_per_video: Number($("costAverageChineseChars")?.value || 500),
    voice_provider: settings.CLOUD_VOICE_PROVIDER || "aliyun_bailian_cosyvoice",
    video_provider: settings.CLOUD_VIDEO_PROVIDER || "fal_latentsync"
  };
  const estimate = await window.aivoDesktop.estimateCloudCost(payload);
  const lines = [
    `货币：${estimate.currency || "USD"}`,
    `声音克隆建档：$${estimate.voice_clone_setup_cost}`,
    `声音合成：$${estimate.voice_synthesis_cost}`,
    `视频渲染：$${estimate.video_render_cost}`,
    `预计月总成本：$${estimate.estimated_monthly_total}`
  ];
  for (const warning of estimate.warnings || []) lines.push(`提醒：${warning}`);
  $("cloudCostEstimate").textContent = lines.join("\n");
  setActionStatus("云端成本估算已更新。", "green");
}

async function showAlignmentReport() {
  setActionStatus("正在生成对齐报告...", "yellow");
  const report = window.aivoDesktop.getSimpleAlignmentReport
    ? await window.aivoDesktop.getSimpleAlignmentReport()
    : await window.aivoDesktop.getAlignmentReport(collect());
  $("alignmentReport").textContent = JSON.stringify(report, null, 2);
}

async function restartBackend() {
  setActionStatus("正在重启后端...", "yellow");
  await saveSettings();
  const backend = await window.aivoDesktop.restartBackend();
  setStatus(backend);
  await refreshLogs();
}

async function stopBackend() {
  setActionStatus("正在停止后端...", "yellow");
  const backend = await window.aivoDesktop.stopBackend();
  setStatus(backend);
  await refreshLogs();
}

async function openStudio() {
  setActionStatus("正在打开工作台...", "yellow");
  const backend = await window.aivoDesktop.openStudio();
  setStatus(backend);
}

async function openTavusConsole() {
  setActionStatus("正在打开 Tavus 控制台...", "yellow");
  await window.aivoDesktop.openExternalUrl("https://platform.tavus.io/");
  setActionStatus("已打开 Tavus 控制台。训练完成后复制 Replica ID 填回这里。", "green");
}

async function openTavusDocs() {
  setActionStatus("正在打开 Tavus 文档...", "yellow");
  await window.aivoDesktop.openExternalUrl("https://docs.tavus.io/");
  setActionStatus("已打开 Tavus 文档。", "green");
}

async function copyTavusReplicaId() {
  const replicaId = $("TAVUS_REPLICA_ID").value.trim();
  if (!replicaId) {
    setActionStatus("当前没有可复制的 Tavus Replica ID。", "yellow");
    $("TAVUS_REPLICA_ID").focus();
    return;
  }
  try {
    await navigator.clipboard.writeText(replicaId);
    setActionStatus("已复制当前 Tavus Replica ID。", "green");
  } catch (_error) {
    setActionStatus(`当前 Tavus Replica ID：${replicaId}`, "yellow");
  }
}

async function refreshLogs() {
  setActionStatus("正在刷新日志...", "yellow");
  $("backendLog").textContent = (await window.aivoDesktop.getLogs()) || "暂无后端日志。";
  setActionStatus("日志已刷新。", "green");
}

async function runAction(message, action) {
  setButtonsDisabled(true);
  setActionStatus(message, "yellow");
  try {
    return await action();
  } catch (error) {
    const text = error && error.message ? error.message : String(error);
    setActionStatus(`操作失败：${text}`, "red");
    $("backendLog").textContent = `${$("backendLog").textContent || ""}\n[设置页] ${text}`;
    return null;
  } finally {
    setButtonsDisabled(false);
  }
}

function setActionStatus(message, status) {
  const summary = $("validationSummary");
  summary.className = `status-line status-${status || "yellow"}`;
  summary.textContent = message;
}

function setButtonsDisabled(disabled) {
  for (const id of actionButtonIds) {
    const button = $(id);
    if (button) button.disabled = disabled;
  }
}

function choosePreset(presetId) {
  selectedPreset = presetId;
  const presets = {
    dryrun_trial: { mode: "dry-run", tts: "dryrun", engine: "static", output: "mp4_only" },
    yuanyue_compat: { mode: "compat", tts: "edge", engine: "syncso", output: "jianying_auto" },
    high_quality: { mode: "final", tts: "aliyun_tts", engine: "latentsync", output: "jianying_auto" },
    batch_production: { mode: "batch", tts: "aliyun_tts", engine: "musetalk", output: "jianying_auto" }
  };
  const preset = presets[presetId] || presets.dryrun_trial;
  $("runtimeMode").value = preset.mode;
  $("ttsProvider").value = preset.tts;
  $("digitalHumanEngine").value = preset.engine;
  $("editingOutput").value = preset.output;
  if (presetId === "high_quality") {
    $("CLOUD_VOICE_PROVIDER").value = "aliyun_bailian_cosyvoice";
    $("CLOUD_VIDEO_PROVIDER").value = "fal_latentsync";
  } else if (presetId === "batch_production") {
    $("CLOUD_VOICE_PROVIDER").value = "aliyun_bailian_cosyvoice";
    $("CLOUD_VIDEO_PROVIDER").value = "fal_musetalk";
  } else if (presetId === "dryrun_trial") {
    $("CLOUD_VOICE_PROVIDER").value = "edge_tts_no_clone";
    $("CLOUD_VIDEO_PROVIDER").value = "local";
  }
  syncSimpleChoicesToAdvanced(true);
  highlightPreset();
  $("envOutput").textContent = toEnvOutput(collect());
  $("validationSummary").className = presetId === "dryrun_trial" ? "status-line status-green" : "status-line status-yellow";
  $("validationSummary").textContent =
    presetId === "dryrun_trial" ? "无需配置，可以体验完整流程，但生成的是占位媒体。" : `已选择：${presetLabels[presetId]}`;
}

function highlightPreset() {
  for (const card of document.querySelectorAll(".usage-card")) {
    card.classList.toggle("active", card.dataset.preset === selectedPreset);
  }
}

function bind() {
  for (const card of document.querySelectorAll(".usage-card")) {
    card.onclick = () => choosePreset(card.dataset.preset);
  }
  for (const id of [...runtimeFields, ...simpleFields, ...textFields]) {
    if ($(id)) $(id).oninput = () => {
      syncSimpleChoicesToAdvanced(true);
      syncMirrorFields();
      $("envOutput").textContent = toEnvOutput(collect());
    };
    if ($(id)) $(id).onchange = () => {
      syncSimpleChoicesToAdvanced(true);
      syncMirrorFields();
      $("envOutput").textContent = toEnvOutput(collect());
    };
  }
  for (const id of checkboxFields) {
    if ($(id)) $(id).onchange = () => {
      $("envOutput").textContent = toEnvOutput(collect());
    };
  }
  $("autoDetectBtn").onclick = () => runAction("正在自动检测...", autoDetectSettings);
  $("applyRecommendedBtn").onclick = () => runAction("正在应用推荐配置，可能需要 10-30 秒...", applyRecommendedConfig);
  $("saveSettingsBtn").onclick = () => runAction("正在保存设置...", saveSettings);
  $("validateSettingsBtn").onclick = () => runAction("正在校验...", validateSettings);
  $("copyEnvBtn").onclick = () => runAction("正在复制 .env...", copyEnvOutput);
  $("alignmentReportBtn").onclick = () => runAction("正在生成对齐报告...", showAlignmentReport);
  $("restartBackendBtn").onclick = () => runAction("正在重启后端...", restartBackend);
  $("stopBackendBtn").onclick = () => runAction("正在停止后端...", stopBackend);
  $("openStudioBtn").onclick = () => runAction("正在打开工作台...", openStudio);
  $("refreshLogBtn").onclick = () => runAction("正在刷新日志...", refreshLogs);
  $("openTavusConsoleBtn").onclick = () => runAction("正在打开 Tavus 控制台...", openTavusConsole);
  $("openTavusDocsBtn").onclick = () => runAction("正在打开 Tavus 文档...", openTavusDocs);
  $("copyTavusReplicaBtn").onclick = () => runAction("正在复制 Replica ID...", copyTavusReplicaId);
  $("estimateCloudCostBtn").onclick = () => runAction("正在估算云端成本...", estimateCloudCost);
}

bind();
load().catch((error) => {
  $("backendLog").textContent = error.message || String(error);
});
