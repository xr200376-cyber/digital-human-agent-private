const state = {
  projectId: "",
  digitalHumanId: "",
  voiceProfileId: "",
  roleModelId: "",
  referenceId: "",
  rewriteId: "",
  selectedRewriteScript: null,
  rewrittenScripts: [],
  campaignId: "",
  publishQueueId: "",
  benchmarkId: "",
  jobId: "",
  taskId: "",
  sourceVideoUploaded: false,
  selectedAvatarAssetId: "",
  videoTemplates: [],
  videoTemplateId: "clean_talking_head",
  modelCatalog: null,
  currentModelSelection: null,
  desktopSettings: null,
  llmPlatforms: null,
  selectedLlmPlatformId: "",
  sourceVideoScript: "",
  sourceVideoHumanRows: [],
  sourceVideoHumanPickerRows: [],
  sourceVideoVoiceRows: [],
  sourceVideoAllVoiceRows: [],
  voiceProfileRows: [],
  sourceVideoAssetPreview: null,
  previewDigitalHumanId: "",
  sourceVideoLastPreparedHumanId: "",
  voicePreviewObjectUrl: "",
  sourceVideoRenderInFlight: false,
  sourceVideoTaskRunning: false,
  sourceVideoRenderBusyLabel: "生成中，请勿重复点击",
  sourceVideoProgressTimer: null,
  sourceVideoProgressValue: 0,
  referenceDownloadWatchId: "",
  referenceDownloadWatchTimer: null,
  remixMainVideos: [],
  selectedRemixMainVideoPath: "",
  remixOutputCount: 1,
  remixAssetPreviewUrls: [],
  sourceVideoPipAssetFiles: [],
  sourceVideoPipAssetPreviewUrls: [],
  sourceVideoSubtitleStyle: {
    font_size: 58,
    color: "#ffffff",
    x: 0.5,
    y: 0.68,
  },
  bgmTracks: [],
  selectedBgmId: "",
  coverTemplates: [],
  selectedCoverTemplateId: "yellow_title_top",
  coverImportObjectUrl: "",
  sourceVideoEditedVideoPath: "",
  sourceVideoEditedVideoUrl: "",
  sourceVideoFinalVideoPath: "",
  sourceVideoFinalVideoUrl: "",
  sourceVideoCoverVideoPath: "",
  sourceVideoCoverTaskId: "",
  sourceVideoCoverPath: "",
  sourceVideoTaskDraftKey: "",
  publishAutomationStatus: null,
  publishAutomationRunning: false,
  desktopLicenseStatus: null,
  creditUsage: null,
};

let activeTextInputContextTarget = null;
let textInputContextMenuBound = false;

const digitalHumanProviderFieldMap = {
  hifly: {
    label: "飞影 API",
    baseUrlKey: "HIFLY_BASE_URL",
    apiKeyKey: "HIFLY_TOKEN",
    defaultBaseUrl: "https://hfw-api.hifly.cc",
  },
  baidu_xiling: {
    label: "百度曦灵",
    baseUrlKey: "BAIDU_XILING_BASE_URL",
    apiKeyKey: "BAIDU_XILING_APP_KEY",
    defaultBaseUrl: "https://open.xiling.baidu.com",
  },
  aliyun_bailian_digital_human: {
    label: "阿里百炼数字人",
    baseUrlKey: "",
    apiKeyKey: "DASHSCOPE_API_KEY",
    defaultBaseUrl: "https://dashscope.aliyuncs.com",
  },
  omnihuman: {
    label: "豆包/火山 OmniHuman",
    baseUrlKey: "OMNIHUMAN_ENDPOINT",
    apiKeyKey: "OMNIHUMAN_ACCESS_KEY",
    defaultBaseUrl: "https://visual.volcengineapi.com",
  },
  tavus: {
    label: "Tavus",
    baseUrlKey: "TAVUS_BASE_URL",
    apiKeyKey: "TAVUS_API_KEY",
    defaultBaseUrl: "https://tavusapi.com",
  },
  syncso: {
    label: "Sync.so",
    baseUrlKey: "SYNCSO_BASE_URL",
    apiKeyKey: "SYNCSO_API_KEY",
    defaultBaseUrl: "https://api.sync.so",
  },
  pixverse_lipsync: {
    label: "PixVerse Lipsync",
    baseUrlKey: "PIXVERSE_BASE_URL",
    apiKeyKey: "PIXVERSE_API_KEY",
    defaultBaseUrl: "https://superaiapi.top",
  },
  fal_musetalk: {
    label: "fal.ai MuseTalk",
    baseUrlKey: "",
    apiKeyKey: "FAL_API_KEY",
    defaultBaseUrl: "https://fal.run",
  },
  fal_latentsync: {
    label: "fal.ai LatentSync",
    baseUrlKey: "",
    apiKeyKey: "FAL_API_KEY",
    defaultBaseUrl: "https://fal.run",
  },
};

const objectStorageBackendLabels = {
  local: "关闭自动上传",
  aliyun_oss: "阿里云 OSS",
  tencent_cos: "腾讯云 COS",
  public_copy: "已有公网目录",
};

const $ = (id) => document.getElementById(id);

function value(id) {
  const element = $(id);
  return element ? element.value.trim() : "";
}

function checked(id) {
  const element = $(id);
  return Boolean(element && element.checked);
}

function sourceVideoCloudGenerationConfirmed() {
  return true;
}

function cloudPaidCallConfirmed() {
  return true;
}

function write(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

function writeJson(id, data) {
  write(id, JSON.stringify(data, null, 2));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function agentStatusElement(target) {
  if (!target) return null;
  return document.querySelector(`[data-agent-status="${target}"]`);
}

function showAgentCardStatus(target, message, kind = "") {
  const element = agentStatusElement(target);
  if (!element) return;
  element.textContent = message;
  element.classList.remove("ok", "warn", "error");
  if (kind) element.classList.add(kind);
}

function showAgentFeatureFailure(feature, target) {
  const name = feature || "该功能";
  showAgentCardStatus(target, `${name}暂未接入真实接口，请先使用已开放的手动流程。`, "error");
}

function bindAgentFailureButtons() {
  for (const button of document.querySelectorAll("[data-fail-feature]")) {
    button.onclick = () => {
      showAgentFeatureFailure(button.dataset.failFeature, button.dataset.agentStatusTarget);
      log(`${button.dataset.failFeature || "功能"}暂未接入真实接口`, "error");
    };
  }
}

function compactText(text, fallback = "") {
  return (text || fallback || "").replace(/\s+/g, " ").trim();
}

const SOURCE_VIDEO_DEFAULT_SCRIPT_ZH = "你好，这是使用源视频音色合成的新口播脚本。原视频声音只作为声音样本，不会直接进入成片。";
const SOURCE_VIDEO_DEFAULT_SCRIPT_EN =
  "Hello, this is a new talking-head script synthesized with the cloned source-video voice. The original video audio is only used as a voice sample and will not be copied into the final video.";
const SOURCE_VIDEO_DEFAULT_SCRIPT_ES =
  "Hola, este es un nuevo guion de video hablado creado con la voz clonada del video fuente. El audio original solo se usa como muestra de voz y no se copia en el video final.";
const SOURCE_VIDEO_DEFAULT_SCRIPT_AR =
  "مرحبا، هذا نص جديد لفيديو متحدث تم إنشاؤه باستخدام نبرة الصوت المستنسخة من الفيديو الأصلي. يستخدم الصوت الأصلي كعينة صوتية فقط ولا يدخل مباشرة في الفيديو النهائي.";
const SOURCE_VIDEO_DEFAULT_SCRIPT_PT =
  "Olá, este é um novo roteiro de vídeo falado criado com a voz clonada do vídeo de origem. O áudio original é usado apenas como amostra de voz e não entra diretamente no vídeo final.";

const SOURCE_VIDEO_LANGUAGE_OPTIONS = {
  "zh-CN": { label: "中文", defaultScript: SOURCE_VIDEO_DEFAULT_SCRIPT_ZH },
  "en-US": { label: "英语", defaultScript: SOURCE_VIDEO_DEFAULT_SCRIPT_EN },
  "es-ES": { label: "西班牙语", defaultScript: SOURCE_VIDEO_DEFAULT_SCRIPT_ES },
  "ar-SA": { label: "阿拉伯语", defaultScript: SOURCE_VIDEO_DEFAULT_SCRIPT_AR },
  "pt-BR": { label: "葡萄牙语", defaultScript: SOURCE_VIDEO_DEFAULT_SCRIPT_PT },
};

function isSourceVideoDefaultScript(text) {
  const raw = compactText(text);
  const normalized = raw.toLowerCase();
  return (
    Object.values(SOURCE_VIDEO_LANGUAGE_OPTIONS).some((option) => compactText(option.defaultScript).toLowerCase() === normalized) ||
    raw.includes("使用源视频音色合成的新口播脚本") ||
    raw.includes("原视频声音只作为声音样本") ||
    isSourceVideoDefaultEnglishScript(raw)
  );
}

function isSourceVideoDefaultEnglishScript(text) {
  const raw = compactText(text).toLowerCase();
  return raw.includes("new talking-head script synthesized") || raw.includes("original video audio is only used as a voice sample");
}

function sourceVideoScriptSeed() {
  const ipInput = compactText(value("sourceVideoIpInput"));
  const script = compactText(value("sourceVideoScript"));
  if (ipInput) return ipInput;
  if (script && !isSourceVideoDefaultScript(script)) return script;
  return "你的产品或服务";
}

function setSourceVideoScriptText(text, message) {
  const scriptBox = $("sourceVideoScript");
  if (scriptBox) scriptBox.value = text;
  state.sourceVideoScript = text;
  updateSourceVideoTextCounters();
  showAgentCardStatus("script", message, "ok");
  log(message, "ok");
}

function sourceVideoCurrentScriptText() {
  const scriptBox = $("sourceVideoScript");
  const current = scriptBox ? String(scriptBox.value || "").trim() : "";
  return current || String(state.sourceVideoScript || "").trim();
}

function syncSourceVideoScriptStateFromInput() {
  const script = sourceVideoCurrentScriptText();
  state.sourceVideoScript = script;
  return script;
}

function sourceVideoCurrentTaskDraftKey(
  script = sourceVideoCurrentScriptText(),
  digitalHumanId = value("sourceVideoHumanSelect") || state.digitalHumanId || "",
  voiceProfileId = value("sourceVideoVoiceSelect") || state.voiceProfileId || "",
) {
  return JSON.stringify({
    script: String(script || "").trim(),
    digital_human_id: digitalHumanId || "",
    voice_profile_id: voiceProfileId || "",
    language: sourceVideoLanguage(),
    voice_style: sourceVideoVoiceStyle(),
    speech_rate: sourceVideoSpeechRate(),
  });
}

function sourceVideoTaskMatchesCurrentDraft() {
  return Boolean(state.taskId && state.sourceVideoTaskDraftKey === sourceVideoCurrentTaskDraftKey());
}

function sourceVideoVisibleCharCount(text) {
  return String(text || "").replace(/\s+/g, "").length;
}

function updateSourceVideoTextCounters() {
  const ipCount = sourceVideoVisibleCharCount(value("sourceVideoIpInput"));
  write("sourceVideoIpCounter", `${ipCount}/10000`);

  const scriptCount = sourceVideoVisibleCharCount(value("sourceVideoScript"));
  write("sourceVideoScriptCounter", `当前脚本：${scriptCount} 字`);
}

function sourceVideoLanguage() {
  const language = value("sourceVideoLanguage") || "zh-CN";
  return SOURCE_VIDEO_LANGUAGE_OPTIONS[language] ? language : "zh-CN";
}

function sourceVideoLanguageLabel() {
  return SOURCE_VIDEO_LANGUAGE_OPTIONS[sourceVideoLanguage()]?.label || "中文";
}

function sourceVideoVoiceStyle() {
  const raw = value("sourceVideoMoodSelect") || "natural";
  const labelMap = {
    自然: "natural",
    热情: "warm",
    沉稳: "calm",
    natural: "natural",
    warm: "warm",
    calm: "calm",
  };
  return labelMap[raw] || "natural";
}

function sourceVideoVoiceStyleLabel() {
  const labels = {
    natural: "自然",
    warm: "热情",
    calm: "沉稳",
  };
  return labels[sourceVideoVoiceStyle()] || "自然";
}

function sourceVideoSpeechRate() {
  const raw = Number(value("sourceVideoSpeechRate") || 1);
  if (!Number.isFinite(raw)) return 1;
  return Math.max(0.5, Math.min(2, Math.round(raw * 10) / 10));
}

function sourceVideoVoiceControls() {
  return {
    voice_style: sourceVideoVoiceStyle(),
    voice_style_label: sourceVideoVoiceStyleLabel(),
    speech_rate: sourceVideoSpeechRate(),
  };
}

function syncSourceVideoVoiceControls() {
  const rate = sourceVideoSpeechRate();
  const rateInput = $("sourceVideoSpeechRate");
  if (rateInput && String(rateInput.value) !== String(rate)) rateInput.value = String(rate);
  const controls = sourceVideoVoiceControls();
  showAgentCardStatus("av", `声音参数已设置：${controls.voice_style_label}，语速 ${controls.speech_rate}x。`, "ok");
}

function sourceVideoDefaultScriptForLanguage() {
  return SOURCE_VIDEO_LANGUAGE_OPTIONS[sourceVideoLanguage()]?.defaultScript || SOURCE_VIDEO_DEFAULT_SCRIPT_ZH;
}

async function syncSourceVideoScriptLanguage() {
  const scriptBox = $("sourceVideoScript");
  if (!scriptBox) return;
  const current = compactText(scriptBox.value);
  if (!current || isSourceVideoDefaultScript(current)) {
    const next = sourceVideoDefaultScriptForLanguage();
    scriptBox.value = next;
    state.sourceVideoScript = next;
    updateSourceVideoTextCounters();
    showAgentCardStatus("script", `文案语言已切换为${sourceVideoLanguageLabel()}，默认示例已同步。`, "ok");
    return;
  }
  updateSourceVideoTextCounters();
  await generateSourceVideoScriptWithCloud("translate");
}

async function translateSourceVideoScriptToCurrentLanguage() {
  await generateSourceVideoScriptWithCloud("translate");
}

function sourceVideoVoicePreviewText() {
  const scriptText = compactText(sourceVideoCurrentScriptText());
  return scriptText || sourceVideoDefaultScriptForLanguage();
}

function sourceVideoScriptActionMeta(mode) {
  if (mode === "rewrite") {
    return {
      mode: "rewrite",
      label: "改写文案",
      running: "正在调用云端大模型改写文案。",
      message: "正在调用当前已配置的大模型改写当前口播文案。",
      style: "文案改写",
      done: "云端大模型已完成文案改写",
      failed: "云端大模型改写失败",
    };
  }
  if (mode === "legal") {
    return {
      mode: "legal",
      label: "AI法务",
      running: "正在调用云端大模型进行 AI法务检查。",
      message: "正在调用当前已配置的大模型规避违规词、夸大词和平台风险词。",
      style: "AI法务合规改写",
      done: "云端大模型已完成 AI法务改写",
      failed: "云端大模型法务检查失败",
    };
  }
  if (mode === "translate") {
    return {
      mode: "translate",
      label: "翻译文案",
      running: "正在调用云端大模型翻译当前文案。",
      message: "正在把当前口播文案翻译为所选语言，并保持原意和口播风格。",
      style: "文案翻译",
      done: "云端大模型已完成文案翻译",
      failed: "云端大模型翻译失败",
    };
  }
  return {
    mode: "generate",
    label: "生成文案",
    running: "正在调用云端大模型生成文案。",
    message: "正在调用当前已配置的大模型生成口播文案。",
    style: "口播成交型",
    done: "云端大模型已生成文案",
    failed: "云端大模型生成失败",
  };
}

async function generateSourceVideoScriptWithCloud(mode = "generate") {
  const action = sourceVideoScriptActionMeta(mode);
  const currentScript = compactText(value("sourceVideoScript"));
  const seed = sourceVideoScriptSeed();
  const topic = action.mode === "generate" ? seed : currentScript || seed;
  if (!topic || topic === "你的产品或服务") {
    showAgentCardStatus("script", action.mode === "generate" ? "请先填写产品主题、品牌资料或参考视频识别内容。" : "请先填写需要处理的脚本文案。", "error");
    return;
  }
  const currentScriptCount = sourceVideoVisibleCharCount(currentScript);
  let targetCharCount = 80;
  if (action.mode === "translate") {
    targetCharCount = null;
  } else if (action.mode === "rewrite" || action.mode === "legal") {
    targetCharCount = Math.max(20, Math.min(2000, currentScriptCount || 80));
  }
  const language = sourceVideoLanguage();
  let lengthNotice = `预计约 ${targetCharCount} 字${sourceVideoLanguageLabel()}。`;
  if (action.mode === "translate") {
    lengthNotice = `将翻译为${sourceVideoLanguageLabel()}，保持原意不扩写。`;
  } else if (action.mode === "rewrite") {
    lengthNotice = `将按原文约 ${targetCharCount} 字轻度改写，不改变主题内容。`;
  }
  showAgentCardStatus("script", `${action.running}${lengthNotice}`, "warn");
  writeJson("sourceVideoProgressBox", {
    status: "running",
    step: "cloud_script_generation",
    message: action.message,
    mode: action.mode,
    topic,
    target_char_count: targetCharCount,
    language,
  });
  try {
    const body = await api("/source-video/script/generate", {
      method: "POST",
      body: JSON.stringify({
        topic,
        project_id: state.projectId || "project_demo",
        platform: "douyin",
        duration_seconds: Math.max(10, Math.min(180, Math.round((targetCharCount || currentScriptCount || 80) / 4))),
        target_char_count: targetCharCount,
        style: action.style,
        current_script: currentScript,
        mode: action.mode,
        language,
        confirm_paid_call: sourceVideoCloudGenerationConfirmed(),
      }),
    });
    const scriptText = (body.script_text || "").trim();
    if (!scriptText) throw new Error("云端模型没有返回可用文案。");
    setSourceVideoScriptText(scriptText, `${action.done}${body.model ? `：${body.model}` : ""}。`);
    writeJson("sourceVideoProgressBox", {
      status: "completed",
      step: "cloud_script_generation",
      mode: action.mode,
      engine: body.engine || "",
      model: body.model || "",
      language,
      fallback_used: Boolean(body.fallback_used),
    });
  } catch (error) {
    const message = error && error.message ? error.message : String(error || "未知错误");
    showAgentCardStatus("script", `${action.failed}：${message}`, "error");
    writeJson("sourceVideoProgressBox", {
      status: "failed",
      step: "cloud_script_generation",
      mode: action.mode,
      message,
    });
    log(`${action.failed}：${message}`, "error");
  }
}

function setSourceVideoTitleTags(data) {
  const title = $("sourceVideoGeneratedTitle");
  const tags = $("sourceVideoGeneratedTags");
  const keywords = $("sourceVideoGeneratedKeywords");
  if (title) title.value = data.title || "";
  if (tags) tags.value = Array.isArray(data.tags) ? data.tags.join(",") : String(data.tags || "");
  if (keywords) {
    keywords.value = Array.isArray(data.keywords) ? data.keywords.join("\n") : String(data.keywords || "");
  }
}

function sourceVideoPublishHashtags() {
  const raw = value("sourceVideoGeneratedTags") || value("sourceVideoGeneratedKeywords") || "";
  return raw
    .split(/[\n,，、#]+/g)
    .map((item) => item.trim().replace(/^#+/, "").replace(/[。.!！?？；;：:]+$/g, ""))
    .filter(Boolean)
    .filter((item, index, rows) => rows.indexOf(item) === index)
    .slice(0, 8);
}

async function generateSourceVideoTitleTagsWithCloud() {
  const ipText = compactText(value("sourceVideoIpInput"));
  const scriptText = compactText(value("sourceVideoScript"));
  if (!ipText && (!scriptText || isSourceVideoDefaultScript(scriptText))) {
    showAgentCardStatus("tags", "请先在卡片 01 粘贴识别内容，或先写好视频文案，再用大模型提取。", "error");
    return;
  }
  const button = $("sourceVideoGenerateTagsBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "大模型提取中...";
  }
  const topic = sourceVideoScriptSeed();
  const extractionText = [ipText, scriptText].filter(Boolean).join("\n\n");
  showAgentCardStatus("tags", "正在调用当前大模型，从识别内容和脚本文案里提取标题标签关键词。", "warn");
  try {
    const body = await api("/source-video/tags/generate", {
      method: "POST",
      body: JSON.stringify({
        topic,
        script_text: extractionText,
        project_id: state.projectId || "project_demo",
        platform: "douyin",
        language: sourceVideoLanguage(),
        confirm_paid_call: sourceVideoCloudGenerationConfirmed(),
      }),
    });
    setSourceVideoTitleTags(body);
    showAgentCardStatus("tags", `已用当前大模型提取标题标签关键词${body.model ? `：${body.model}` : ""}。`, "ok");
    log("标题标签关键词已用大模型提取。", "ok");
  } catch (error) {
    const message = error && error.message ? error.message : String(error || "未知错误");
    showAgentCardStatus("tags", `大模型提取标题标签失败：${message}`, "error");
    log(`大模型提取标题标签失败：${message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "提取标题标签关键词";
    }
  }
}

function buildSourceVideoHotScript(seed) {
  const subject = compactText(seed, "我们的产品").slice(0, 90).replace(/[。！？,.，、；;：:]+$/g, "");
  if (sourceVideoLanguage() === "en-US") {
    return [
      `When people look for ${subject}, they often ask for the price first, but price is not the only thing that decides the result.`,
      `What really matters is whether the specs, delivery, quality, and after-sales support are reliable.`,
      `If you are comparing options, focus on the use case, quantity, timeline, and the risks you want to avoid.`,
      `Send us your requirement, and we will help you match a practical solution before you make a bulk decision.`,
    ].join("\n");
  }
  const profile = sourceVideoTopicProfile(subject);
  return [
    `做${subject}，很多人第一反应只问价格，但真正影响成交的往往不是单价。`,
    `${profile.audience}更关心的是：${profile.pain}。`,
    `所以选择${subject}，要看${profile.checkpoints}，这样后面补货、交付和售后才省心。`,
    `${profile.value}。`,
    `如果你正在找稳定的${subject}渠道，可以先把需求、数量和使用场景发来，我们帮你快速核一版方案。`,
  ].join("\n");
}

function buildSourceVideoGeneratedScript(seed) {
  const subject = compactText(seed, "这项服务").slice(0, 120).replace(/[。！？,.，、；;：:]+$/g, "");
  if (sourceVideoLanguage() === "en-US") {
    return [
      `Hi everyone, today I want to talk about ${subject}.`,
      `If you are comparing suppliers or service options, do not only look at the surface price.`,
      `You also need to check quality, delivery, support, and whether the solution really fits your use case.`,
      `Tell us your requirement and budget, and we can help you compare a more practical option.`,
    ].join("\n");
  }
  const profile = sourceVideoTopicProfile(subject);
  return [
    `大家好，今天给大家介绍${subject}。`,
    `如果你是${profile.audience}，采购时一定不要只看表面报价。`,
    `更要提前确认${profile.checkpoints}，因为这些细节会直接影响后期交付、使用效果和售后成本。`,
    `我们的优势是${profile.value}，可以根据你的数量、规格和使用场景，快速匹配更合适的方案。`,
    `${profile.proof}。`,
    `需要了解${subject}，可以直接留言或私信，把需求发来，我们给你做一版参考报价。`,
  ].join("\n");
}

function sourceVideoTopicProfile(subject) {
  const text = compactText(subject).toLowerCase();
  if (/瓷砖|地砖|墙砖|岩板|通体砖|抛釉砖|建材|装修材料/.test(text)) {
    return {
      audience: "装修公司、工长、建材门店、工程采购和正在装修的客户",
      pain: "怕规格不全、色号批次不稳、补货慢、运输破损、售后沟通麻烦",
      checkpoints: "规格型号、材质工艺、花色批次、库存数量、送货时效和破损补发规则",
      value: "常用规格可批量供应，花色选择多，适合门店零售、工程配套和整装项目采购",
      proof: "你可以先看样品、核对色号和铺贴场景，再决定批量拿货",
    };
  }
  if (/批发|供应|厂家|货源|代理|招商|渠道/.test(text)) {
    return {
      audience: "门店老板、渠道商、工程采购和需要稳定货源的客户",
      pain: "怕价格不透明、库存不稳定、交付慢、售后无人跟进",
      checkpoints: "供货周期、起订数量、价格梯度、库存稳定性和售后规则",
      value: "可以按采购量和使用场景匹配货源，帮助你降低沟通成本和试错成本",
      proof: "建议先确认样品、规格、数量和交付时间，再进入正式采购",
    };
  }
  return {
    audience: "正在比较方案、需要解决实际问题的客户",
    pain: "怕信息不清楚、价格和效果不匹配、后续服务跟不上",
    checkpoints: "适用场景、核心优势、交付方式、服务保障和真实案例",
    value: `我们会围绕${subject}的真实需求，提供更清楚、更容易落地的方案`,
    proof: "你可以先说明自己的需求和预算，我们再给出更具体的建议",
  };
}

async function applySourceVideoScriptAction(action) {
  if (action === "hot") {
    setSourceVideoScriptText(buildSourceVideoHotScript(sourceVideoScriptSeed()), "已在当前页生成爆款口播文案。");
    showAgentCardStatus("ip", "文案仿写已填入下方脚本框，无需跳转页面。", "ok");
    return;
  }
  if (action === "legal") {
    await generateSourceVideoScriptWithCloud("legal");
    return;
  }
  if (action === "rewrite") {
    await generateSourceVideoScriptWithCloud("rewrite");
    return;
  }
  if (action === "generate") {
    await generateSourceVideoScriptWithCloud();
    return;
  }
  showAgentCardStatus("script", "暂不支持该文案操作。", "error");
}

function sourceVideoReferenceCaptureText(capture) {
  const lines = [];
  if (capture.platform) lines.push(`平台：${capture.platform}`);
  if (capture.source_url) lines.push(`来源链接：${capture.source_url}`);
  if (capture.title) lines.push(`标题：${capture.title}`);
  if (capture.description) lines.push(`文案：${capture.description}`);
  if (capture.video_url) lines.push(`公开视频：${capture.video_url}`);
  return lines.join("\n").trim() || capture.content_text || "";
}

function extractFirstHttpUrl(text) {
  const match = String(text || "").match(/https?:\/\/[^\s"'<>，。；;、]+/i);
  return match ? match[0].trim() : "";
}

function sourceVideoReferenceLinkFromInput() {
  return extractFirstHttpUrl(value("sourceVideoReferenceLinkInput")) || extractFirstHttpUrl(value("sourceVideoIpInput"));
}

function applySourceVideoReferenceCapture(capture) {
  const input = $("sourceVideoIpInput");
  const collectedText = sourceVideoReferenceCaptureText(capture);
  if (input && collectedText) {
    const current = compactText(input.value);
    input.value = current ? `${input.value.trim()}\n\n${collectedText}` : collectedText;
  }
  if (capture.script_seed && (!compactText(value("sourceVideoScript")) || isSourceVideoDefaultScript(value("sourceVideoScript")))) {
    setSourceVideoScriptText(capture.script_seed, "平台链接文案已同步到视频文案编辑区。");
  }
  writeJson("sourceVideoProgressBox", {
    status: capture.status,
    step: "reference_link_collection",
    platform: capture.platform,
    title: capture.title || "",
    downloadable: Boolean(capture.downloadable),
    message: capture.message || "",
    recommended_next_action: capture.recommended_next_action || "",
  });
  if (capture.status === "captured") {
    showAgentCardStatus("ip", "平台链接已采集，可继续点击文案仿写或改写文案。", "ok");
    return;
  }
  showAgentCardStatus("ip", `平台限制：${capture.recommended_next_action || "请手动下载参考视频后上传。"}`, "error");
}

function setSourceVideoReferenceLinkStatus(message, kind = "") {
  const box = $("sourceVideoReferenceLinkStatus");
  if (!box) return;
  box.textContent = message;
  box.classList.remove("ok", "warn", "error");
  if (kind) box.classList.add(kind);
}

function focusSourceVideoReferenceLinkInput(prefillUrl) {
  const input = $("sourceVideoReferenceLinkInput");
  const url = prefillUrl || sourceVideoReferenceLinkFromInput();
  if (input) {
    if (url && !compactText(input.value)) input.value = url;
    setTimeout(() => input.focus(), 30);
  }
  setSourceVideoReferenceLinkStatus(
    url
      ? "已带入链接。点击“开始解析并转写”，本地视频解析服务会先尝试拿到公开视频文件。"
      : "请粘贴公开视频链接；如果平台限制无法读取，请先下载视频后上传。",
    url ? "warn" : ""
  );
}

function sourceVideoReferenceLinkValue() {
  return sourceVideoReferenceLinkFromInput();
}

function sourceVideoReferenceLinkRawValue() {
  return compactText(value("sourceVideoReferenceLinkInput")) || compactText(value("sourceVideoIpInput"));
}

function applySourceVideoReferenceTranscription(result) {
  const collection = result.collection || {};
  if (collection && collection.source_url) {
    applySourceVideoReferenceCapture(collection);
  }
  const transcript = compactText(result.transcript_text || "");
  writeJson("sourceVideoProgressBox", {
    status: result.status,
    step: "reference_link_transcription",
    platform: result.platform,
    source_url: result.source_url,
    reference_id: result.reference_id,
    message: result.message || "",
    recommended_next_action: result.recommended_next_action || "",
  });
  if (result.status === "transcribed" && transcript) {
    const input = $("sourceVideoIpInput");
    if (input) {
      const current = compactText(input.value);
      const block = `FunASR转写文案：\n${transcript}`;
      input.value = current ? `${input.value.trim()}\n\n${block}` : block;
    }
    setSourceVideoScriptText(transcript, "FunASR 已把视频声音转写到脚本文案。");
    showAgentCardStatus("ip", "视频声音已转写成文案，并同步到下方脚本框。", "ok");
    setSourceVideoReferenceLinkStatus("转写完成，已同步到当前页面。", "ok");
    return;
  }
  const message =
    result.message ||
    (transcript
      ? "转写状态异常，未覆盖脚本文案。"
      : "没有拿到视频声音转写稿，未覆盖脚本文案。请检查 FunASR / Paraformer 或上传本地视频。");
  const nextMessage = `${message} 可以点击“接收客户端下载”，然后在抖音客户端点官方下载。`;
  showAgentCardStatus("ip", nextMessage, "error");
  setSourceVideoReferenceLinkStatus(nextMessage, "error");
}

async function transcribeSourceVideoReferenceLink() {
  const url = sourceVideoReferenceLinkValue();
  if (!url) {
    const raw = sourceVideoReferenceLinkRawValue();
    setSourceVideoReferenceLinkStatus(
      raw
        ? "没有检测到 http 或 https 视频链接。平台口令不能直接读取，请复制完整网页链接，或下载视频后上传。"
        : "请先粘贴视频链接。",
      "error"
    );
    return;
  }
  const button = $("sourceVideoReferenceLinkAnalyzeBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "解析中...";
  }
  setSourceVideoReferenceLinkStatus("正在调用本地视频解析服务；如果拿到视频文件，会继续下载、抽音频并转写。", "warn");
  showAgentCardStatus("ip", "正在解析视频链接并准备转写声音。", "warn");
  try {
    const parseResult = await api(`/projects/${encodeURIComponent(state.projectId || "project_demo")}/reference-links/parse`, {
      method: "POST",
      body: JSON.stringify({
        url: url.trim(),
        metadata: {
          source: "agent_workbench_reference_link_inline",
        },
      }),
    });
    writeJson("sourceVideoProgressBox", {
      status: parseResult.status,
      step: "reference_link_parse",
      engine: parseResult.engine,
      platform: parseResult.platform,
      downloadable: parseResult.downloadable,
      message: parseResult.message || "",
    });
    if (parseResult.status === "parsed") {
      setSourceVideoReferenceLinkStatus("本地视频解析成功，正在下载视频、抽音频并转写。", "warn");
    } else {
      setSourceVideoReferenceLinkStatus(parseResult.message || "本地解析未拿到视频文件，将继续尝试转写链路。", "warn");
    }
    const result = await api(`/projects/${encodeURIComponent(state.projectId || "project_demo")}/reference-links/transcribe`, {
      method: "POST",
      body: JSON.stringify({
        url: url.trim(),
        asr_engine: "funasr",
        metadata: {
          fallback_text: value("sourceVideoIpInput") || value("sourceVideoScript"),
          source: "agent_workbench_reference_link_inline",
        },
      }),
    });
    applySourceVideoReferenceTranscription(result);
    log(result.status === "transcribed" ? "参考视频声音已转写。" : "参考视频链接无法直接转写。", result.status === "transcribed" ? "ok" : "error");
  } catch (error) {
    const message = error && error.message ? error.message : String(error || "未知错误");
    setSourceVideoReferenceLinkStatus(`链接转写失败：${message}`, "error");
    showAgentCardStatus("ip", `链接转写失败：${message}`, "error");
    writeJson("sourceVideoProgressBox", {
      status: "failed",
      step: "reference_link_transcription",
      message,
    });
    log(`链接转写失败：${message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "开始解析并转写";
    }
  }
}

function stopSourceVideoReferenceDownloadWatch() {
  if (state.referenceDownloadWatchTimer) {
    window.clearInterval(state.referenceDownloadWatchTimer);
    state.referenceDownloadWatchTimer = null;
  }
  const button = $("sourceVideoDownloadWatchBtn");
  if (button) {
    button.disabled = false;
    button.textContent = "接收客户端下载";
  }
}

async function pollSourceVideoReferenceDownloadWatch() {
  if (!state.referenceDownloadWatchId) return;
  const body = await api(
    `/projects/${encodeURIComponent(state.projectId || "project_demo")}/reference-links/download-watch/${encodeURIComponent(state.referenceDownloadWatchId)}`
  );
  writeJson("sourceVideoProgressBox", {
    status: body.status,
    step: "reference_download_watch",
    platform: body.platform,
    message: body.message || "",
    candidate_path: body.candidate_path || "",
  });
  if (body.status === "completed" && body.result) {
    stopSourceVideoReferenceDownloadWatch();
    state.referenceDownloadWatchId = "";
    applySourceVideoReferenceTranscription(body.result);
    log("抖音客户端下载视频已自动导入并转写。", "ok");
    return;
  }
  if (body.status === "failed" || body.status === "expired") {
    stopSourceVideoReferenceDownloadWatch();
    state.referenceDownloadWatchId = "";
    const message = body.message || "没有接收到可转写的视频，请重新在抖音客户端点官方下载。";
    setSourceVideoReferenceLinkStatus(message, "error");
    showAgentCardStatus("ip", message, "error");
    log(message, "error");
    return;
  }
  const message = body.message || "正在等待抖音客户端下载视频。";
  setSourceVideoReferenceLinkStatus(message, "warn");
  showAgentCardStatus("ip", message, "warn");
}

async function startSourceVideoReferenceDownloadWatch() {
  stopSourceVideoReferenceDownloadWatch();
  const url = sourceVideoReferenceLinkValue();
  const button = $("sourceVideoDownloadWatchBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "等待下载...";
  }
  setSourceVideoReferenceLinkStatus("已开启下载接收。请在抖音客户端点击官方下载，完成后会自动转写。", "warn");
  showAgentCardStatus("ip", "正在等待抖音客户端下载视频。", "warn");
  try {
    const body = await api(`/projects/${encodeURIComponent(state.projectId || "project_demo")}/reference-links/download-watch/start`, {
      method: "POST",
      body: JSON.stringify({
        url: url || "",
        platform: "douyin",
        asr_engine: "funasr",
        metadata: {
          source: "douyin_client_download_watch",
          fallback_text: value("sourceVideoIpInput") || value("sourceVideoScript"),
        },
      }),
    });
    state.referenceDownloadWatchId = body.watch_id || "";
    writeJson("sourceVideoProgressBox", {
      status: body.status,
      step: "reference_download_watch",
      platform: body.platform,
      message: body.message || "",
      download_dir: body.download_dir || "",
    });
    state.referenceDownloadWatchTimer = window.setInterval(() => {
      safeRun(pollSourceVideoReferenceDownloadWatch);
    }, 2000);
    await pollSourceVideoReferenceDownloadWatch();
  } catch (error) {
    stopSourceVideoReferenceDownloadWatch();
    state.referenceDownloadWatchId = "";
    const message = error && error.message ? error.message : String(error || "未知错误");
    setSourceVideoReferenceLinkStatus(`接收客户端下载失败：${message}`, "error");
    showAgentCardStatus("ip", `接收客户端下载失败：${message}`, "error");
    log(`接收客户端下载失败：${message}`, "error");
  }
}

function collectSourceVideoReferenceLink() {
  focusSourceVideoReferenceLinkInput();
}

function bindInlineSourceVideoScriptActions() {
  for (const button of document.querySelectorAll("[data-inline-script-action]")) {
    button.onclick = () => {
      const action = button.dataset.inlineScriptAction;
      for (const item of document.querySelectorAll(".agent-tabs button")) item.classList.remove("active");
      if (action === "hot") button.classList.add("active");
      safeRun(() => applySourceVideoScriptAction(action));
    };
  }
}

function toggleStudioTheme() {
  document.body.classList.toggle("light-theme");
  const button = $("themeToggleBtn");
  if (button) button.textContent = document.body.classList.contains("light-theme") ? "换肤 深色" : "换肤 浅色";
}

async function runAgentAutoMode() {
  showAgentCardStatus("script", "正在保存脚本。", "warn");
  showAgentCardStatus("av", "正在检查数字人和声音。", "warn");
  const script = value("sourceVideoScript");
  if (!script) {
    showAgentCardStatus("script", "请先填写视频脚本。", "error");
    throw new Error("请先填写视频脚本。");
  }
  if (!value("sourceVideoHumanSelect")) {
    showAgentCardStatus("av", "请先选择可制作的数字人形象。", "error");
    throw new Error("请先选择可制作的数字人形象。");
  }
  if (!value("sourceVideoVoiceSelect")) {
    showAgentCardStatus("av", "请先选择声音。", "error");
    throw new Error("请先选择声音。");
  }
  await saveSourceVideoScript();
  showAgentCardStatus("script", "脚本已保存，字幕默认跟随脚本文案。", "ok");
  showAgentCardStatus("av", "正在生成数字人视频。", "warn");
  await renderSourceVideoTask();
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",").pop() : result);
    };
    reader.onerror = () => reject(reader.error || new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

function setFileInputFiles(input, files) {
  if (!input || !files || !files.length) return false;
  try {
    const transfer = new DataTransfer();
    for (const file of files) transfer.items.add(file);
    input.files = transfer.files;
    return true;
  } catch (_error) {
    return false;
  }
}

function updateSourceVideoDropStatus(message, kind = "") {
  const hint = $("sourceVideoDropHint");
  if (hint) hint.textContent = message;
  const zone = $("sourceVideoDropZone");
  if (zone) {
    zone.classList.toggle("drag-ready", kind === "ready");
    zone.classList.toggle("drag-error", kind === "error");
  }
  if (kind === "error") log(message, "error");
}

function sourceVideoFileFromDrop(event) {
  const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []);
  if (!files.length) {
    throw new Error("没有收到真实视频文件。请先把视频保存到本地文件夹，再从文件夹拖到这里。");
  }
  const file = files.find((item) => (item.type || "").startsWith("video/")) || files[0];
  const name = (file.name || "").toLowerCase();
  const looksLikeVideo =
    (file.type || "").startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(name);
  if (!looksLikeVideo) {
    throw new Error("拖入的文件不是视频文件，请选择 MP4、MOV、WEBM、MKV 或 AVI。");
  }
  return file;
}

function handleSourceVideoDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  const zone = $("sourceVideoDropZone");
  if (zone) zone.classList.remove("drag-ready");
  try {
    const file = sourceVideoFileFromDrop(event);
    const input = $("sourceVideoFile");
    if (!setFileInputFiles(input, [file])) {
      throw new Error("当前系统不允许把拖拽文件写入上传框，请点击上传区域手动选择这个视频。");
    }
    updateSourceVideoDropStatus(`已选择视频：${file.name}。点击“立即克隆”开始上传。`, "ready");
  } catch (error) {
    updateSourceVideoDropStatus(error.message || String(error), "error");
  }
}

function bindSourceVideoDropZone() {
  const zone = $("sourceVideoDropZone");
  const input = $("sourceVideoFile");
  if (!zone || !input) return;
  for (const eventName of ["dragenter", "dragover"]) {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      zone.classList.add("drag-ready");
      zone.classList.remove("drag-error");
    });
  }
  for (const eventName of ["dragleave", "dragend"]) {
    zone.addEventListener(eventName, () => {
      zone.classList.remove("drag-ready");
    });
  }
  zone.addEventListener("drop", handleSourceVideoDrop);
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (file) updateSourceVideoDropStatus(`已选择视频：${file.name}。点击“立即克隆”开始上传。`, "ready");
  });
  for (const eventName of ["dragover", "drop"]) {
    window.addEventListener(eventName, (event) => {
      if (event.target && zone.contains(event.target)) return;
      event.preventDefault();
    });
  }
}

function setVideoRemixCount(count) {
  state.remixOutputCount = Number(count) || 1;
  for (const button of document.querySelectorAll("[data-remix-count]")) {
    button.classList.toggle("active", button.dataset.remixCount === String(state.remixOutputCount));
  }
  writeJson("videoRemixStatusBox", {
    "状态": "未开始",
    "提示": "已选择生成数量，点击“一键生成混剪视频”后开始。",
    "生成数量": state.remixOutputCount,
  });
}

function clearRemixMainVideoPreview(message = "请选择一个成片视频") {
  const preview = $("remixMainVideoPreview");
  const empty = $("remixMainVideoEmptyPreview");
  if (preview) {
    preview.pause();
    preview.removeAttribute("src");
    preview.load();
  }
  if (empty) {
    empty.textContent = message;
    empty.classList.remove("is-hidden");
  }
  write("remixMainVideoName", "未选择");
}

function selectRemixMainVideo(video) {
  if (!video || !video.path) return;
  state.selectedRemixMainVideoPath = video.path;
  state.selectedRemixMainVideoScript = video.script_text || "";
  const select = $("remixMainVideoSelect");
  if (select) select.value = video.path;
  for (const card of document.querySelectorAll(".remix-video-card")) {
    card.classList.toggle("selected", card.dataset.path === video.path);
  }
  const preview = $("remixMainVideoPreview");
  const empty = $("remixMainVideoEmptyPreview");
  if (preview && video.preview_url) {
    preview.src = video.preview_url;
    preview.classList.remove("is-hidden");
    if (empty) empty.classList.add("is-hidden");
  }
  write("remixMainVideoName", `${video.display_name || video.label || "成片视频"} · ${video.kind_label || "成片视频"}`);
  const subtitleInput = $("remixSubtitleText");
  if (subtitleInput) {
    subtitleInput.placeholder = video.script_preview
      ? `不填则自动跟随：${video.script_preview}`
      : "不填则自动跟随成片脚本";
  }
}

function clearVideoRemixResult(message = "生成完成后，这里会显示混剪结果。") {
  const preview = $("videoRemixOutputPreview");
  const empty = $("videoRemixOutputEmptyPreview");
  if (preview) {
    preview.pause();
    preview.removeAttribute("src");
    preview.load();
    preview.classList.add("is-hidden");
  }
  if (empty) {
    empty.textContent = message;
    empty.classList.remove("is-hidden");
  }
  const link = $("downloadVideoRemixOutput");
  if (link) {
    link.removeAttribute("href");
    link.classList.add("disabled");
    link.textContent = "下载混剪结果";
  }
}

function videoRemixDownloadUrl(url) {
  if (!url) return "";
  return `${url}${url.includes("?") ? "&" : "?"}download=1`;
}

function renderVideoRemixResult(body) {
  const outputUrls = body && Array.isArray(body.output_urls) ? body.output_urls : [];
  const fallbackOutputs = body && Array.isArray(body.outputs) ? body.outputs : [];
  const firstUrl = outputUrls[0] || (fallbackOutputs[0] ? `/video-remix/output-preview?path=${encodeURIComponent(fallbackOutputs[0])}` : "");
  if (!firstUrl) {
    clearVideoRemixResult("混剪已提交，但还没有可预览的结果视频。");
    return;
  }
  const preview = $("videoRemixOutputPreview");
  const empty = $("videoRemixOutputEmptyPreview");
  if (preview) {
    preview.src = firstUrl;
    preview.classList.remove("is-hidden");
    preview.load();
  }
  if (empty) empty.classList.add("is-hidden");
  setDownload("downloadVideoRemixOutput", videoRemixDownloadUrl(firstUrl));
}

function renderVideoRemixMainVideoCards(videos) {
  const box = $("remixMainVideoCards");
  if (!box) return;
  box.innerHTML = "";
  if (!videos || !videos.length) {
    box.className = "remix-video-grid empty";
    box.textContent = "暂无可选成片视频，请先生成数字人成片或上传本地成片视频。";
    clearRemixMainVideoPreview();
    return;
  }
  box.className = "remix-video-grid";
  for (const video of videos) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "remix-video-card";
    card.dataset.path = video.path || "";
    const thumb = document.createElement("span");
    thumb.className = "remix-video-thumb";
    const preview = document.createElement("video");
    preview.src = video.preview_url || "";
    preview.muted = true;
    preview.playsInline = true;
    preview.preload = "metadata";
    thumb.appendChild(preview);
    const title = document.createElement("strong");
    title.textContent = video.display_name || video.label || "成片视频";
    const meta = document.createElement("span");
    meta.textContent = video.kind_label || "成片视频";
    card.appendChild(thumb);
    card.appendChild(title);
    card.appendChild(meta);
    card.onclick = () => selectRemixMainVideo(video);
    box.appendChild(card);
  }
}

function renderRemixAssetPreview(files) {
  const box = $("remixAssetPreviewGrid");
  if (!box) return;
  for (const url of state.remixAssetPreviewUrls || []) URL.revokeObjectURL(url);
  state.remixAssetPreviewUrls = [];
  box.innerHTML = "";
  const selectedFiles = Array.from(files || []);
  if (!selectedFiles.length) {
    box.className = "remix-asset-preview-grid empty";
    box.textContent = "暂未选择素材。建议上传 2-6 张产品图、案例图或素材视频。";
    return;
  }
  box.className = "remix-asset-preview-grid";
  selectedFiles.forEach((file, index) => {
    const card = document.createElement("div");
    card.className = "remix-asset-card";
    const thumb = document.createElement("span");
    thumb.className = "remix-asset-thumb";
    const url = URL.createObjectURL(file);
    state.remixAssetPreviewUrls.push(url);
    if ((file.type || "").startsWith("video/")) {
      const video = document.createElement("video");
      video.src = url;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      thumb.appendChild(video);
    } else if ((file.type || "").startsWith("image/")) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = file.name || `素材 ${index + 1}`;
      thumb.appendChild(image);
    } else {
      thumb.textContent = "文件";
    }
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${file.name || "未命名素材"}`;
    const meta = document.createElement("span");
    meta.textContent = (file.type || "未知类型").replace("/", " / ");
    card.appendChild(thumb);
    card.appendChild(title);
    card.appendChild(meta);
    box.appendChild(card);
  });
  writeJson("videoRemixStatusBox", {
    "状态": "素材已选择",
    "提示": "默认只生成一条；前8秒和最后3秒保留口播数字人，中间按上传顺序连续播放素材。",
    "素材数量": selectedFiles.length,
    "生成数量": state.remixOutputCount || 1,
  });
}

function openSourceVideoPipModal() {
  const checkbox = $("sourceVideoPipEnabled");
  if (checkbox) checkbox.checked = true;
  showModal("sourceVideoPipModal", true);
  renderSourceVideoPipAssetPreview();
  showAgentCardStatus("edit", "请在弹窗中选择画中画素材；前8秒和最后3秒保留口播数字人，中间按上传顺序连续播放素材。", "warn");
}

function closeSourceVideoPipModal() {
  showModal("sourceVideoPipModal", false);
  const count = (state.sourceVideoPipAssetFiles || []).length;
  showAgentCardStatus("edit", count ? `已选择 ${count} 个画中画素材。` : "画中画素材尚未选择。", count ? "ok" : "warn");
}

function toggleSourceVideoPipSettings() {
  openSourceVideoPipModal();
}

const SOURCE_VIDEO_FIXED_SUBTITLE_STYLE = Object.freeze({
  font_size: 58,
  color: "#ffffff",
  x: 0.5,
  y: 0.68,
});

function sourceVideoSubtitleStylePayload() {
  const style = { ...SOURCE_VIDEO_FIXED_SUBTITLE_STYLE };
  state.sourceVideoSubtitleStyle = style;
  return style;
}

function sourceVideoPipFileKey(file) {
  return [file.name || "", file.size || 0, file.lastModified || 0, file.type || ""].join("::");
}

function addSourceVideoPipAssetFiles(files) {
  const incoming = Array.from(files || []);
  if (!incoming.length) return;
  const existing = new Set((state.sourceVideoPipAssetFiles || []).map(sourceVideoPipFileKey));
  for (const file of incoming) {
    const key = sourceVideoPipFileKey(file);
    if (existing.has(key)) continue;
    state.sourceVideoPipAssetFiles.push(file);
    existing.add(key);
  }
  renderSourceVideoPipAssetPreview();
}

function removeSourceVideoPipAsset(index) {
  state.sourceVideoPipAssetFiles.splice(index, 1);
  renderSourceVideoPipAssetPreview();
}

function clearSourceVideoPipAssets() {
  state.sourceVideoPipAssetFiles = [];
  const input = $("sourceVideoPipAssetFiles");
  if (input) input.value = "";
  renderSourceVideoPipAssetPreview();
  showAgentCardStatus("edit", "已清空画中画素材。", "warn");
}

function pickMoreSourceVideoPipAssets() {
  const input = $("sourceVideoPipAssetFiles");
  if (input) input.click();
}

function renderSourceVideoPipAssetPreview() {
  const box = $("sourceVideoPipAssetPreviewGrid");
  if (!box) return;
  for (const url of state.sourceVideoPipAssetPreviewUrls || []) URL.revokeObjectURL(url);
  state.sourceVideoPipAssetPreviewUrls = [];
  box.innerHTML = "";
  const selectedFiles = Array.from(state.sourceVideoPipAssetFiles || []);
  if (!selectedFiles.length) {
    box.className = "remix-asset-preview-grid empty";
    box.textContent = "暂未选择素材。可一次上传多张产品图、案例图或素材视频。";
    return;
  }
  box.className = "remix-asset-preview-grid";
  selectedFiles.forEach((file, index) => {
    const card = document.createElement("div");
    card.className = "remix-asset-card";
    const thumb = document.createElement("span");
    thumb.className = "remix-asset-thumb";
    const url = URL.createObjectURL(file);
    state.sourceVideoPipAssetPreviewUrls.push(url);
    if ((file.type || "").startsWith("video/")) {
      const video = document.createElement("video");
      video.src = url;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      thumb.appendChild(video);
    } else if ((file.type || "").startsWith("image/")) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = file.name || `素材 ${index + 1}`;
      thumb.appendChild(image);
    } else {
      thumb.textContent = "文件";
    }
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${file.name || "未命名素材"}`;
    const meta = document.createElement("span");
    meta.textContent = (file.type || "未知类型").replace("/", " / ");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remix-asset-remove";
    remove.textContent = "移除";
    remove.onclick = () => removeSourceVideoPipAsset(index);
    card.append(thumb, title, meta, remove);
    box.appendChild(card);
  });
  showAgentCardStatus("edit", `已累计 ${selectedFiles.length} 个画中画素材，可继续添加或直接生成。`, "warn");
}

function currentSourceVideoTaskId() {
  if (state.taskId) return state.taskId;
  const preview = $("sourceVideoFinalPreview");
  const src = preview ? preview.currentSrc || preview.src || "" : "";
  const match = src.match(/\/tasks\/([^/]+)\/download\/final-video/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function currentSourceVideoMainPayload() {
  const taskId = currentSourceVideoTaskId();
  if (taskId) {
    const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/download/final-video`);
    if (response.ok) {
      const blob = await response.blob();
      if (blob && blob.size > 0) {
        return {
          main_video_path: "",
          main_video: await fileUploadPayload(new File([blob], `数字人成片-${taskId}.mp4`, { type: blob.type || "video/mp4" })),
        };
      }
    }
  }

  await refreshVideoRemixMainVideos();
  const selected =
    state.remixMainVideos.find((video) => taskId && String(video.path || "").includes(taskId)) ||
    state.remixMainVideos[0];
  if (selected && selected.path) {
    return { main_video_path: selected.path, main_video: null };
  }
  throw new Error("请先生成数字人口播成片，再生成画中画。");
}

function renderSourceVideoPipOutput(body) {
  const outputUrls = body && Array.isArray(body.output_urls) ? body.output_urls : [];
  const fallbackOutputs = body && Array.isArray(body.outputs) ? body.outputs : [];
  const firstUrl = outputUrls[0] || (fallbackOutputs[0] ? `/video-remix/output-preview?path=${encodeURIComponent(fallbackOutputs[0])}` : "");
  if (!firstUrl) {
    showAgentCardStatus("edit", "画中画字幕成片已提交，但暂时没有可预览的视频。", "warn");
    return;
  }
  state.sourceVideoEditedVideoPath = fallbackOutputs[0] || parseStoragePathFromPreviewUrl(firstUrl) || "";
  state.sourceVideoEditedVideoUrl = firstUrl;
  state.sourceVideoFinalVideoPath = "";
  state.sourceVideoFinalVideoUrl = "";
  state.sourceVideoCoverVideoPath = fallbackOutputs[0] || "";
  state.sourceVideoCoverTaskId = "";
  state.sourceVideoCoverPath = "";
  const preview = $("sourceVideoFinalPreview");
  if (preview) {
    preview.src = firstUrl;
    preview.load();
  }
  setDownload("downloadSourceVideoPipOutput", videoRemixDownloadUrl(firstUrl));
  const link = $("downloadSourceVideoPipOutput");
  if (link) link.textContent = "下载画中画字幕成片";
  showAgentCardStatus("subtitle", "卡片 03 已完成，可以在卡片 05 添加背景音乐并导出最终结果。", "ok");
}

function sourceVideoSubtitleText() {
  return value("sourceVideoSubtitleText") || sourceVideoCurrentScriptText() || null;
}

function findBgmTrack(trackId) {
  const selectedId = String(trackId || "").trim();
  if (!selectedId) return null;
  return (state.bgmTracks || []).find((track) => track.id === selectedId && track.available !== false) || null;
}

function selectedBgmTrack() {
  const selectedId = state.selectedBgmId || value("sourceVideoBgmSelect");
  return findBgmTrack(selectedId);
}

function formatBgmSize(sizeBytes) {
  const size = Number(sizeBytes || 0);
  if (!Number.isFinite(size) || size <= 0) return "未知大小";
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`;
  return `${Math.max(1, Math.round(size / 1024))}KB`;
}

function sourceVideoBgmVolumeValue() {
  const input = $("sourceVideoBgmVolume");
  const raw = Number(input?.value || 18);
  const percent = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 18;
  return Number((percent / 100).toFixed(2));
}

function syncBgmAudioVolumeFromHiddenInput() {
  const audio = $("sourceVideoBgmAudio");
  if (!audio || audio.dataset.bgmVolumeInitialized === "true") return;
  audio.volume = sourceVideoBgmVolumeValue();
  audio.dataset.bgmVolumeInitialized = "true";
}

function syncBgmHiddenVolumeFromAudio() {
  const audio = $("sourceVideoBgmAudio");
  const input = $("sourceVideoBgmVolume");
  if (!audio || !input) return;
  input.value = String(Math.round(Math.max(0, Math.min(1, audio.volume)) * 100));
}

function bindBgmNativeVolumeControl() {
  const audio = $("sourceVideoBgmAudio");
  if (!audio) return;
  syncBgmAudioVolumeFromHiddenInput();
  audio.onvolumechange = syncBgmHiddenVolumeFromAudio;
}

function updateBgmSelectionDisplay() {
  const track = selectedBgmTrack();
  const current = $("sourceVideoBgmCurrent");
  if (current) {
    if (track) {
      current.textContent = `${track.title_cn || track.title} · ${track.mood || "口播背景乐"}`;
    } else {
      current.textContent = "暂未选择背景音乐";
    }
  }
  const select = $("sourceVideoBgmSelect");
  if (select && track) select.value = track.id;
}

function renderBgmLibrary() {
  const select = $("sourceVideoBgmSelect");
  if (!select) return;
  const tracks = Array.isArray(state.bgmTracks) ? state.bgmTracks.filter((track) => track.available !== false) : [];
  select.innerHTML = "";
  if (!tracks.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无可用背景音乐";
    select.appendChild(option);
    updateBgmSelectionDisplay();
    renderBgmPickerModal();
    showAgentCardStatus("subtitle", "背景音乐库为空，请检查 app/static/bgm。", "warn");
    return;
  }
  for (const track of tracks) {
    const option = document.createElement("option");
    option.value = track.id;
    option.textContent = `${track.title_cn || track.title} · ${track.mood || "口播背景乐"}`;
    select.appendChild(option);
  }
  if (!state.selectedBgmId || !tracks.some((track) => track.id === state.selectedBgmId)) {
    state.selectedBgmId = tracks[0].id;
  }
  select.value = state.selectedBgmId;
  updateBgmSelectionDisplay();
  renderBgmPickerModal();
  updateBgmPreview(false);
}

async function loadBgmLibrary() {
  if (!$("sourceVideoBgmSelect")) return;
  try {
    const body = await api("/bgm/library");
    state.bgmTracks = Array.isArray(body.tracks) ? body.tracks : [];
    renderBgmLibrary();
    if (state.bgmTracks.length) {
      showAgentCardStatus("subtitle", "背景音乐已加载，可选择试听；卡片 05 会把它混入最终结果。", "ok");
    }
  } catch (error) {
    state.bgmTracks = [];
    renderBgmLibrary();
    showAgentCardStatus("subtitle", `背景音乐加载失败：${error.message || error}`, "error");
  }
}

function updateBgmPreview(autoplay = false) {
  const track = selectedBgmTrack();
  const audio = $("sourceVideoBgmAudio");
  if (!track || !audio) return;
  state.selectedBgmId = track.id;
  const select = $("sourceVideoBgmSelect");
  if (select) select.value = track.id;
  updateBgmSelectionDisplay();
  renderBgmPickerModal();
  syncBgmAudioVolumeFromHiddenInput();
  const nextUrl = `${track.url}${track.url.includes("?") ? "&" : "?"}v=${Date.now()}`;
  if (audio.dataset.trackId !== track.id) {
    audio.src = nextUrl;
    audio.dataset.trackId = track.id;
    audio.load();
  }
  showAgentCardStatus(
    "subtitle",
    `已选择背景音乐：${track.title_cn || track.title}。导出最终结果时会以低音量混入，不盖住人声。`,
    "ok",
  );
  if (autoplay) {
    audio.play().catch(() => {
      showAgentCardStatus("subtitle", "浏览器阻止了自动播放，请点击播放器播放按钮试听。", "warn");
    });
  }
}

function previewBgmTrack(trackId) {
  const track = findBgmTrack(trackId);
  const audio = $("sourceVideoBgmAudio");
  if (!track || !audio) {
    showAgentCardStatus("subtitle", "这首背景音乐暂不可用，请选择其他配乐。", "warn");
    return;
  }
  syncBgmAudioVolumeFromHiddenInput();
  const nextUrl = `${track.url}${track.url.includes("?") ? "&" : "?"}v=${Date.now()}`;
  if (audio.dataset.trackId !== track.id) {
    audio.src = nextUrl;
    audio.dataset.trackId = track.id;
    audio.load();
  }
  showAgentCardStatus("subtitle", `正在试听：${track.title_cn || track.title}。满意后点击“选择”。`, "ok");
  audio.play().catch(() => {
    showAgentCardStatus("subtitle", "浏览器阻止了自动播放，请点击播放器播放按钮试听。", "warn");
  });
}

function selectBgmTrack(trackId, autoplay = false, closeModal = false) {
  const track = findBgmTrack(trackId);
  if (!track) {
    showAgentCardStatus("subtitle", "这首背景音乐暂不可用，请选择其他配乐。", "warn");
    return;
  }
  state.selectedBgmId = track.id;
  const select = $("sourceVideoBgmSelect");
  if (select) select.value = track.id;
  updateBgmPreview(autoplay);
  if (closeModal) closeBgmPickerModal();
}

function handleBgmPickerAction(event) {
  const button = event.target.closest("[data-bgm-action][data-bgm-id]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  const trackId = button.dataset.bgmId;
  if (button.dataset.bgmAction === "preview") {
    previewBgmTrack(trackId);
    return;
  }
  if (button.dataset.bgmAction === "select") {
    selectBgmTrack(trackId, false, true);
  }
}

function renderBgmPickerModal() {
  const box = $("sourceVideoBgmModalList");
  if (!box) return;
  const tracks = Array.isArray(state.bgmTracks) ? state.bgmTracks.filter((track) => track.available !== false) : [];
  if (!tracks.length) {
    box.className = "bgm-picker-list empty";
    box.textContent = "暂无可用背景音乐。";
    return;
  }
  box.className = "bgm-picker-list";
  box.innerHTML = "";
  for (const track of tracks) {
    const row = document.createElement("div");
    row.className = `bgm-picker-row${track.id === state.selectedBgmId ? " selected" : ""}`;
    row.dataset.bgmId = track.id;
    const meta = document.createElement("div");
    meta.className = "bgm-picker-meta";
    const title = document.createElement("strong");
    title.textContent = track.title_cn || track.title || track.id;
    const desc = document.createElement("span");
    desc.textContent = `${track.mood || "口播背景乐"} · ${formatBgmSize(track.size_bytes)}`;
    meta.append(title, desc);

    const actions = document.createElement("div");
    actions.className = "bgm-picker-actions";
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.textContent = "试听";
    previewButton.dataset.bgmId = track.id;
    previewButton.dataset.bgmAction = "preview";
    previewButton.setAttribute("aria-label", `试听 ${track.title_cn || track.title || track.id}`);
    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.textContent = track.id === state.selectedBgmId ? "已选择" : "选择";
    selectButton.className = track.id === state.selectedBgmId ? "active" : "";
    selectButton.dataset.bgmId = track.id;
    selectButton.dataset.bgmAction = "select";
    selectButton.setAttribute("aria-label", `选择 ${track.title_cn || track.title || track.id}`);
    actions.append(previewButton, selectButton);
    row.append(meta, actions);
    row.ondblclick = () => selectBgmTrack(row.dataset.bgmId, false, true);
    box.appendChild(row);
  }
}

function openBgmPickerModal() {
  renderBgmPickerModal();
  showModal("sourceVideoBgmModal", true);
}

function closeBgmPickerModal() {
  showModal("sourceVideoBgmModal", false);
}

function previewSelectedBgm() {
  if (!selectedBgmTrack()) {
    showAgentCardStatus("subtitle", "请先选择一首背景音乐。", "warn");
    return;
  }
  updateBgmPreview(true);
}

function sourceVideoBgmPayload() {
  const track = selectedBgmTrack();
  const enabled = checked("sourceVideoBgmEnabled") && Boolean(track);
  return {
    add_background_music: enabled,
    background_music_id: enabled ? track.id : null,
    background_music_volume: sourceVideoBgmVolumeValue(),
  };
}

function currentSourceVideoEditedVideoPath() {
  if (state.sourceVideoEditedVideoPath) return state.sourceVideoEditedVideoPath;
  const preview = $("sourceVideoFinalPreview");
  const src = preview ? preview.currentSrc || preview.src || "" : "";
  return parseStoragePathFromPreviewUrl(src);
}

function renderSourceVideoBgmFinalOutput(body) {
  const outputUrls = body && Array.isArray(body.output_urls) ? body.output_urls : [];
  const fallbackOutputs = body && Array.isArray(body.outputs) ? body.outputs : [];
  const firstUrl = outputUrls[0] || (fallbackOutputs[0] ? `/video-remix/output-preview?path=${encodeURIComponent(fallbackOutputs[0])}` : "");
  if (!firstUrl) {
    showAgentCardStatus("subtitle", "配乐已提交，但暂时没有可预览的视频。", "warn");
    return;
  }
  state.sourceVideoFinalVideoPath = fallbackOutputs[0] || parseStoragePathFromPreviewUrl(firstUrl) || "";
  state.sourceVideoFinalVideoUrl = firstUrl;
  state.sourceVideoCoverVideoPath = state.sourceVideoFinalVideoPath || state.sourceVideoEditedVideoPath || "";
  state.sourceVideoCoverTaskId = "";
  state.sourceVideoCoverPath = "";
  const preview = $("sourceVideoMusicFinalPreview");
  if (preview) {
    preview.src = firstUrl;
    preview.load();
  }
  setDownload("downloadSourceVideoFinal", videoRemixDownloadUrl(firstUrl));
  showAgentCardStatus("subtitle", "最终结果已导出，已包含卡片 03 的画中画字幕和卡片 05 的背景音乐。", "ok");
}

function selectedCoverTemplate() {
  return (state.coverTemplates || []).find((template) => template.template_id === state.selectedCoverTemplateId) || null;
}

function updateCoverTemplateSummary() {
  const template = selectedCoverTemplate();
  const summary = $("sourceVideoCoverTemplateSummary");
  if (!summary) return;
  if (!template) {
    summary.textContent = "未选择模板";
    return;
  }
  summary.textContent = `${template.name || template.template_id} · ${template.preview || "首帧关键词封面"}`;
}

function renderCoverTemplates() {
  const box = $("sourceVideoCoverTemplateModalGrid");
  updateCoverTemplateSummary();
  if (!box) return;
  box.innerHTML = "";
  const templates = Array.isArray(state.coverTemplates) ? state.coverTemplates : [];
  if (!templates.length) {
    box.className = "cover-template-grid cover-template-modal-grid empty";
    box.textContent = "暂无封面模板。";
    showAgentCardStatus("cover", "封面模板加载失败，请刷新页面。", "error");
    return;
  }
  box.className = "cover-template-grid cover-template-modal-grid";
  if (!templates.some((template) => template.template_id === state.selectedCoverTemplateId)) {
    state.selectedCoverTemplateId = templates[0].template_id;
  }
  updateCoverTemplateSummary();
  for (const template of templates) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "cover-template-card";
    card.dataset.templateId = template.template_id;
    card.classList.toggle("selected", template.template_id === state.selectedCoverTemplateId);
    card.style.borderColor = template.accent || "";
    const image = document.createElement("img");
    image.className = "cover-template-preview-image";
    image.src = template.preview_image || "";
    image.alt = template.name || "封面模板";
    const title = document.createElement("strong");
    title.textContent = template.name || template.template_id;
    const desc = document.createElement("span");
    desc.textContent = template.preview || template.description || "封面模板";
    card.append(image, title, desc);
    card.onclick = () => selectCoverTemplate(template.template_id);
    box.appendChild(card);
  }
}

async function loadCoverTemplates() {
  if (!$("sourceVideoCoverTemplateSummary") && !$("sourceVideoCoverTemplateModalGrid")) return;
  try {
    const body = await api("/cover/templates");
    state.coverTemplates = Array.isArray(body.templates) ? body.templates : [];
    renderCoverTemplates();
    showAgentCardStatus("cover", "封面模板已加载，选择模板后可用视频首帧生成封面。", "ok");
  } catch (error) {
    state.coverTemplates = [];
    renderCoverTemplates();
    showAgentCardStatus("cover", `封面模板加载失败：${error.message || error}`, "error");
  }
}

function selectCoverTemplate(templateId) {
  state.selectedCoverTemplateId = templateId;
  renderCoverTemplates();
  const template = selectedCoverTemplate();
  showAgentCardStatus("cover", `已选择封面模板：${template ? template.name : templateId}`, "ok");
}

async function openCoverSettingsModal() {
  showModal("coverSettingsModal", true);
  if (!Array.isArray(state.coverTemplates) || !state.coverTemplates.length) {
    await loadCoverTemplates();
  } else {
    renderCoverTemplates();
  }
}

function closeCoverSettingsModal() {
  showModal("coverSettingsModal", false);
}

function coverPreviewImageIsReady(image) {
  if (!image) return false;
  const source = image.currentSrc || image.src || "";
  const preview = image.closest(".cover-preview");
  return Boolean(source && preview && preview.classList.contains("has-image"));
}

function openCoverPreviewModal() {
  const image = $("sourceVideoCoverPreviewImage");
  if (!coverPreviewImageIsReady(image)) {
    showAgentCardStatus("cover", "请先生成或导入封面，再放大查看。", "warn");
    return;
  }
  const modalImage = $("coverPreviewModalImage");
  if (modalImage) {
    modalImage.src = image.currentSrc || image.src;
    modalImage.alt = image.alt || "封面大图预览";
  }
  showModal("coverPreviewModal", true);
}

function closeCoverPreviewModal() {
  showModal("coverPreviewModal", false);
}

function handleCoverPreviewKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  safeRun(openCoverPreviewModal);
}

function renderImportedCover(file, objectUrl) {
  const image = $("sourceVideoCoverPreviewImage");
  const preview = image ? image.closest(".cover-preview") : null;
  if (image) {
    image.src = objectUrl;
    image.alt = "本地导入封面预览";
    if (preview) preview.classList.add("has-image");
  }
  const importPreview = $("sourceVideoCoverImportPreview");
  if (importPreview) {
    importPreview.innerHTML = "";
    const imported = document.createElement("img");
    imported.src = objectUrl;
    imported.alt = "本地导入封面预览";
    const label = document.createElement("span");
    label.textContent = file.name;
    importPreview.append(imported, label);
    importPreview.classList.add("has-image");
  }
  const download = $("downloadSourceVideoCover");
  if (download) {
    download.href = objectUrl;
    download.download = file.name || "cover.png";
    download.classList.remove("disabled");
  }
  showAgentCardStatus("cover", "已导入本地封面图，可直接作为当前封面使用，不会上传云端。", "ok");
}

function importLocalCoverImage() {
  const input = $("sourceVideoCoverImportFile");
  const file = input && input.files && input.files[0];
  if (!file) return;
  if (!file.type || !file.type.startsWith("image/")) {
    showAgentCardStatus("cover", "请选择 PNG、JPG 或 WebP 图片作为封面。", "error");
    if (input) input.value = "";
    return;
  }
  if (state.coverImportObjectUrl) URL.revokeObjectURL(state.coverImportObjectUrl);
  state.coverImportObjectUrl = URL.createObjectURL(file);
  state.sourceVideoCoverPath = "";
  renderImportedCover(file, state.coverImportObjectUrl);
}

function chooseLocalCoverImage() {
  const input = $("sourceVideoCoverImportFile");
  if (input) input.click();
}

function sourceVideoCoverKeyword() {
  return (
    sourceVideoGeneratedKeywordText() ||
    value("sourceVideoGeneratedTitle") ||
    sourceVideoScriptSeed() ||
    "数字人口播"
  ).slice(0, 80);
}

function sourceVideoKeywordLines() {
  return String(value("sourceVideoGeneratedKeywords") || "")
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceVideoGeneratedKeywordText() {
  return sourceVideoKeywordLines().slice(0, 2).join(" ");
}

function parseStoragePathFromPreviewUrl(url) {
  if (!url) return "";
  try {
    const parsed = new URL(url, window.location.origin);
    if (parsed.pathname === "/video-remix/output-preview") {
      return parsed.searchParams.get("path") || "";
    }
  } catch (_error) {
    return "";
  }
  return "";
}

async function currentCoverVideoPayload() {
  if (state.sourceVideoCoverVideoPath) {
    return { video_path: state.sourceVideoCoverVideoPath };
  }
  if (state.sourceVideoCoverTaskId || currentSourceVideoTaskId()) {
    return { task_id: state.sourceVideoCoverTaskId || currentSourceVideoTaskId() };
  }
  const preview = $("sourceVideoFinalPreview");
  const src = preview ? preview.currentSrc || preview.src || "" : "";
  const remixPath = parseStoragePathFromPreviewUrl(src);
  if (remixPath) return { video_path: remixPath };
  const mainPayload = await currentSourceVideoMainPayload();
  if (mainPayload.main_video_path) return { video_path: mainPayload.main_video_path };
  return { video: mainPayload.main_video };
}

function renderCoverResult(body) {
  state.sourceVideoCoverPath = body.cover_path || "";
  const image = $("sourceVideoCoverPreviewImage");
  const preview = image ? image.closest(".cover-preview") : null;
  if (image && body.cover_url) {
    image.src = `${body.cover_url}${body.cover_url.includes("?") ? "&" : "?"}v=${Date.now()}`;
    image.alt = "生成封面预览";
    if (preview) preview.classList.add("has-image");
  }
  setDownload("downloadSourceVideoCover", body.cover_url ? `${body.cover_url}&download=1` : "");
}

async function generateSourceVideoCover() {
  const button = $("sourceVideoGenerateCoverBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "生成中...";
  }
  try {
    const videoPayload = await currentCoverVideoPayload();
    const payload = {
      project_id: state.projectId || value("projectId") || "project_demo",
      template_id: state.selectedCoverTemplateId || "yellow_title_top",
      keyword_text: sourceVideoCoverKeyword(),
      ...videoPayload,
    };
    showAgentCardStatus("cover", "正在提取视频首帧并生成封面。", "warn");
    const body = await api("/cover/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderCoverResult(body);
    showAgentCardStatus("cover", `封面已生成：${body.template_name} / ${body.keyword_text}`, "ok");
    log(body.message || "封面已生成。", "ok");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "用首帧生成封面";
    }
  }
}

async function createSourceVideoPipRemixTask() {
  requireProject();
  if (!checked("sourceVideoPipEnabled")) throw new Error("请先勾选画中画。");
  const generateButton = $("sourceVideoPipGenerateBtn");
  const assetFiles = Array.from(state.sourceVideoPipAssetFiles || []);
  if (!assetFiles.length) throw new Error("请先上传至少一个画中画素材。");

  if (generateButton) {
    generateButton.disabled = true;
    generateButton.textContent = "生成中...";
  }
  setSourceVideoProgress(92, "正在生成画中画字幕成片", "正在把素材插入口播成片，并按脚本文案生成字幕，请不要重复点击。", "running");
  showAgentCardStatus("edit", "画中画和字幕正在当前页面生成，请稍等。", "warn");
  writeJson("sourceVideoProgressBox", {
    "状态": "画中画字幕生成中",
    "提示": "正在本地混剪：前8秒和最后3秒保留口播数字人，中间按上传顺序连续播放素材，字幕会在本步骤生成。",
    "素材数量": assetFiles.length,
    "生成数量": 1,
    "字幕": checked("sourceVideoSubtitleEnabled") ? "卡片03生成字幕" : "不添加字幕",
    "背景音乐": "卡片05单独添加",
  });

  try {
    const mainPayload = await currentSourceVideoMainPayload();
    const payload = {
      project_id: state.projectId || value("projectId") || "project_demo",
      main_video_path: mainPayload.main_video_path || "",
      main_video: mainPayload.main_video || null,
      assets: [],
      output_count: 1,
      add_subtitles: checked("sourceVideoSubtitleEnabled"),
      use_smart_subtitles: checked("sourceVideoSmartSubtitleEnabled"),
      subtitle_text: sourceVideoSubtitleText(),
      subtitle_style: sourceVideoSubtitleStylePayload(),
      add_background_music: false,
      background_music_id: null,
      background_music_volume: 0,
    };
    for (const file of assetFiles) {
      payload.assets.push(await fileUploadPayload(file));
    }
    const body = await api("/video-remix/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    writeJson("sourceVideoProgressBox", body);
    renderSourceVideoPipOutput(body);
    setSourceVideoProgress(100, "画中画字幕生成完成", "画中画字幕成片已生成，可到卡片 05 添加配乐并导出最终结果。", "done");
    showAgentCardStatus("edit", "画中画字幕成片已生成，可在当前卡片预览和下载。", "ok");
    log(body.message || `画中画字幕成片已完成：${body.remix_task_id || ""}`, "ok");
  } catch (error) {
    const message = error.message || String(error);
    writeJson("sourceVideoProgressBox", {
      "状态": "画中画字幕生成失败",
      "错误": message,
      "建议": "请减少素材数量或关闭智能字幕后重试。",
    });
    setSourceVideoProgress(0, "画中画字幕生成失败", message, "error");
    showAgentCardStatus("edit", message, "error");
    log(message, "error");
  } finally {
    if (generateButton) {
      generateButton.disabled = false;
      generateButton.textContent = "生成画中画字幕成片";
    }
  }
}

async function createSourceVideoBgmFinalTask() {
  requireProject();
  const button = $("sourceVideoAddBgmBtn");
  const editedVideoPath = currentSourceVideoEditedVideoPath();
  if (!editedVideoPath) {
    throw new Error("请先完成卡片 03，生成画中画字幕成片后再添加配乐。");
  }
  const editedVideoUrl =
    state.sourceVideoEditedVideoUrl ||
    `/video-remix/output-preview?path=${encodeURIComponent(editedVideoPath)}`;
  const bgmPayload = sourceVideoBgmPayload();
  if (!bgmPayload.add_background_music) {
    state.sourceVideoFinalVideoPath = editedVideoPath;
    state.sourceVideoFinalVideoUrl = editedVideoUrl;
    state.sourceVideoCoverVideoPath = editedVideoPath;
    state.sourceVideoCoverTaskId = "";
    state.sourceVideoCoverPath = "";
    const preview = $("sourceVideoMusicFinalPreview");
    if (preview) {
      preview.src = editedVideoUrl;
      preview.load();
    }
    setDownload("downloadSourceVideoFinal", videoRemixDownloadUrl(editedVideoUrl));
    showAgentCardStatus("subtitle", "未添加背景音乐，已把卡片 03 的画中画字幕成片作为最终结果。", "warn");
    return;
  }

  if (button) {
    button.disabled = true;
    button.textContent = "导出中...";
  }
  showAgentCardStatus("subtitle", "正在给卡片 03 的处理后视频添加背景音乐并导出最终结果。", "warn");
  try {
    const payload = {
      project_id: state.projectId || value("projectId") || "project_demo",
      main_video_path: editedVideoPath,
      main_video: null,
      assets: [],
      output_count: 1,
      add_subtitles: false,
      use_smart_subtitles: false,
      subtitle_text: null,
      ...bgmPayload,
    };
    const body = await api("/video-remix/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderSourceVideoBgmFinalOutput(body);
    log(body.message || `最终配乐成片已完成：${body.remix_task_id || ""}`, "ok");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "添加配乐并导出最终结果";
    }
  }
}

async function refreshVideoRemixMainVideos() {
  const projectId = state.projectId || value("projectId") || "project_demo";
  const body = await api(`/video-remix/main-videos?project_id=${encodeURIComponent(projectId)}`);
  state.remixMainVideos = body.videos || [];
  fillSelect($("remixMainVideoSelect"), state.remixMainVideos, "path", "label", "选择成片视频");
  renderVideoRemixMainVideoCards(state.remixMainVideos);
  const selected =
    state.remixMainVideos.find((video) => video.path === state.selectedRemixMainVideoPath) ||
    state.remixMainVideos[0];
  if (selected) selectRemixMainVideo(selected);
  writeJson("videoRemixStatusBox", {
    "状态": "可生成",
    "提示": "已加载成片视频，选择素材后点击“一键生成混剪视频”。",
    "成片数量": state.remixMainVideos.length,
  });
}

async function fileUploadPayload(file) {
  return {
    filename: file.name || "upload.bin",
    content_type: file.type || "application/octet-stream",
    content_base64: await readFileAsBase64(file),
  };
}

function log(message, kind = "") {
  const box = $("logBox");
  const time = new Date().toLocaleTimeString("zh-CN");
  if (box) {
    box.textContent += `[${time}] ${message}\n`;
    box.scrollTop = box.scrollHeight;
  }
  if (kind) {
    write("taskStatus", message);
    const status = $("taskStatus");
    if (status) status.className = kind;
  }
}

function updateSourceVideoRenderButton() {
  const button = $("sourceVideoRenderBtn");
  if (!button) return;
  button.disabled = Boolean(state.sourceVideoRenderInFlight || state.sourceVideoTaskRunning);
  if (state.sourceVideoRenderInFlight) {
    button.textContent = state.sourceVideoRenderBusyLabel || "生成中，请勿重复点击";
  } else if (state.sourceVideoTaskRunning) {
    button.textContent = "任务运行中，请等待";
  } else {
    button.textContent = "生成数字人视频";
  }
}

function stopSourceVideoProgressTicker() {
  if (state.sourceVideoProgressTimer) {
    window.clearInterval(state.sourceVideoProgressTimer);
    state.sourceVideoProgressTimer = null;
  }
}

function setSourceVideoProgress(percent, title, hint, status = "running") {
  const value = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
  state.sourceVideoProgressValue = value;
  const wrap = $("sourceVideoProgressWrap");
  const bar = $("sourceVideoProgressBar");
  const fill = $("sourceVideoProgressFill");
  if (wrap) wrap.className = `source-progress ${status || ""}`.trim();
  if (bar) bar.setAttribute("aria-valuenow", String(value));
  if (fill) fill.style.width = `${value}%`;
  write("sourceVideoProgressPercent", `${value}%`);
  if (title) write("sourceVideoProgressTitle", title);
  if (hint) write("sourceVideoProgressHint", hint);
  if (title || hint) {
    const kind = status === "done" ? "ok" : status === "error" ? "error" : "warn";
    showAgentCardStatus("av", `${title || "制作进度"}：${hint || `${value}%`}`, kind);
  }
}

function startSourceVideoProgressTicker(title = "云端生成中", hint = "正在等待云端返回成片，请保持窗口打开。", startAt = 65, ceiling = 92) {
  stopSourceVideoProgressTicker();
  if (state.sourceVideoProgressValue < startAt) setSourceVideoProgress(startAt, title, hint, "running");
  state.sourceVideoProgressTimer = window.setInterval(() => {
    const current = state.sourceVideoProgressValue || 0;
    if (current >= ceiling) return;
    const step = current < 80 ? 3 : 1;
    setSourceVideoProgress(Math.min(ceiling, current + step), title, hint, "running");
  }, 1400);
}

function finishSourceVideoProgress(success, message) {
  stopSourceVideoProgressTicker();
  if (success) {
    setSourceVideoProgress(100, "生成完成", message || "数字人视频已生成，可以预览或下载。", "done");
    return;
  }
  setSourceVideoProgress(100, "生成失败", message || "生成失败，请查看报告或稍后重试。", "error");
}

function setSourceVideoRenderBusy(isBusy, label = "生成中，请勿重复点击") {
  state.sourceVideoRenderInFlight = Boolean(isBusy);
  state.sourceVideoRenderBusyLabel = label;
  updateSourceVideoRenderButton();
}

function setSourceVideoTaskRunning(isRunning) {
  state.sourceVideoTaskRunning = Boolean(isRunning);
  updateSourceVideoRenderButton();
}

function sourceVideoRenderFriendlyError(error) {
  const message = error && error.message ? error.message : String(error || "");
  if (message.includes("confirm_paid_call=true required") || message.includes("credit-consuming API call")) {
    return "云端生成确认未生效，请刷新页面后重新点击生成。真实云端生成可能消耗服务额度。";
  }
  if (message.includes("409") || message.includes("已有数字人生成任务正在运行") || message.includes("当前数字人生成任务正在运行")) {
    return "已有数字人生成任务正在运行，请等待当前任务完成后再提交。";
  }
  if (message.includes("429") || message.includes("Too Many Requests")) {
    return "平台限流，请等待 10-30 分钟后再试；请不要连续点击生成。";
  }
  if (
    message.includes("UserDisable") ||
    message.includes("x-oss-request-id") ||
    message.includes("aliyuncs.com") ||
    (message.includes("403") && (message.includes("OSS") || message.includes("oss")))
  ) {
    return "阿里云 OSS 上传失败：OSS 服务当前不可用，可能是未开通、欠费、账号被禁用或 Bucket 权限异常。请先在阿里云控制台恢复 OSS，或改用可公网访问的对象存储后重试。";
  }
  return "";
}

async function refreshSourceVideoRunningTaskStatus() {
  const body = await api("/tasks/running");
  const tasks = body.tasks || [];
  setSourceVideoTaskRunning(tasks.length > 0);
  if (tasks.length > 0) {
    startSourceVideoProgressTicker("任务运行中", "已有数字人视频任务正在生成，请等待完成。", 70, 92);
  }
  return tasks;
}

function customerFacingApiError(detail) {
  const message = typeof detail === "string" ? detail : JSON.stringify(detail || "");
  const map = {
    license_credit_insufficient: "积分不足，请充值或购买正式版后继续使用。",
    license_usage_limit_reached: "积分不足，请充值或购买正式版后继续使用。",
    license_usage_limit_insufficient: "积分不足，请充值或购买正式版后继续使用。",
    activation_token_invalid: "授权已失效，请重新激活后继续使用。",
    license_disabled: "授权已停用，请联系管理员。",
    license_expired: "授权已过期，请续费后继续使用。",
  };
  return map[message] || message;
}

async function responseErrorDetail(response) {
  const text = await response.text();
  try {
    const parsed = JSON.parse(text);
    return customerFacingApiError(parsed.detail || parsed.error || parsed.message || text);
  } catch (_error) {
    return customerFacingApiError(text);
  }
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData ? options.headers || {} : { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const detail = await responseErrorDetail(response);
    throw new Error(detail || `请求失败：${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function desktopAppVersion() {
  return "0.1.0";
}

function setDesktopLicenseGateVisible(visible) {
  const gate = $("desktopLicenseGate");
  if (gate) gate.classList.toggle("hidden", !visible);
}

function writeDesktopLicenseStatus(message, kind = "") {
  const element = $("desktopLicenseStatusText");
  if (!element) return;
  element.textContent = message;
  element.classList.remove("ok", "warn", "error");
  if (kind) element.classList.add(kind);
}

function formatCreditNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return Math.round(number).toLocaleString("zh-CN");
}

const CREDIT_FEATURE_LABELS = {
  aliyun_voice_clone: "阿里云声音克隆",
  aliyun_voice_preview: "阿里云语音试听",
  hifly_avatar: "飞影形象创建",
  hifly_voice: "飞影声音克隆",
  hifly_video: "飞影数字人视频",
  cloud_video_render: "云端数字人视频",
  legacy_usage_claim: "历史用量扣除",
  manual_payment: "购买到账",
  cycle_refresh: "周期刷新",
  admin_adjust: "后台调整",
  trial_delivery: "试用版开通",
  paid_delivery: "正式版开通",
};

const CREDIT_PROVIDER_LABELS = {
  aliyun: "阿里云",
  hifly: "飞影",
  syncso: "Sync.so",
  omnihuman: "火山 OmniHuman",
  pixverse: "PixVerse",
  cloud_video_render: "云端视频",
};

function creditProviderLabel(provider) {
  const key = String(provider || "").trim().toLowerCase();
  return CREDIT_PROVIDER_LABELS[key] || provider || "";
}

function creditFeatureLabel(value, row = {}) {
  const raw = String(value || "").trim();
  if (!raw) {
    return CREDIT_FEATURE_LABELS[row.type] || creditProviderLabel(row.provider) || "云端生成";
  }
  const [base, suffix] = raw.split(":", 2);
  const label = CREDIT_FEATURE_LABELS[base] || CREDIT_FEATURE_LABELS[raw] || creditProviderLabel(base) || raw;
  if (base === "cloud_video_render" && suffix) {
    const provider = creditProviderLabel(suffix);
    return provider ? `${provider}数字人视频` : label;
  }
  return label;
}

function creditTransactionAmount(row, status) {
  if (status === "committed") return row.credits_committed || Math.abs(row.delta_credits || 0);
  if (status === "refunded") return row.credits_refunded || Math.abs(row.delta_credits || 0);
  if (status === "reserved") return row.credits_reserved || Math.abs(row.delta_credits || 0);
  return row.delta_credits || row.credits_committed || row.credits_refunded || row.credits_reserved || 0;
}

function creditTransactionDetail(row) {
  const parts = [];
  const seconds = Number(row.seconds || 0);
  const rate = Number(row.rate_per_second || 0);
  const provider = creditProviderLabel(row.provider);
  if (seconds > 0) parts.push(`计费 ${formatCreditNumber(seconds)} 秒`);
  if (rate > 0) parts.push(`${formatCreditNumber(rate)} 积分/秒`);
  if (provider) parts.push(`平台：${provider}`);
  if (Number(row.credits_refunded || 0) > 0) parts.push(`已退回 ${formatCreditNumber(row.credits_refunded)} 积分`);
  return parts.join(" · ");
}

function formatCreditTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function creditSnapshotFromStatus(status) {
  const credits = status && typeof status.credits === "object" ? status.credits : {};
  return credits || {};
}

function renderCreditBalance(status) {
  const button = $("creditBalanceBtn");
  if (!button) return;
  const allowed = Boolean(status && status.allowed);
  const credits = creditSnapshotFromStatus(status);
  const hasCredits = Object.prototype.hasOwnProperty.call(credits, "balance");
  button.hidden = !allowed || !hasCredits;
  if (button.hidden) return;
  const locked = Boolean(credits.locked || credits.lock_reason);
  button.textContent = locked ? "积分不足" : `积分 ${formatCreditNumber(credits.balance)}`;
  button.classList.toggle("warn", locked);
  button.title = "查看积分消耗";
}

function setCreditUsageDialogVisible(visible) {
  const dialog = $("creditUsageDialog");
  if (dialog) dialog.classList.toggle("hidden", !visible);
}

function creditTransactionTitle(row) {
  const status = String(row.status || "");
  const type = String(row.type || "");
  const feature = creditFeatureLabel(row.feature || row.reason || row.provider || type, row);
  if (status === "committed") return `${feature} 扣除 ${formatCreditNumber(creditTransactionAmount(row, status))} 积分`;
  if (status === "refunded") return `${feature} 退回 ${formatCreditNumber(creditTransactionAmount(row, status))} 积分`;
  if (status === "reserved") return `${feature} 预占 ${formatCreditNumber(creditTransactionAmount(row, status))} 积分`;
  if (type === "manual_payment") return `购买/开通到账 ${formatCreditNumber(row.delta_credits || 0)} 积分`;
  if (type === "cycle_refresh") return `周期刷新 ${formatCreditNumber(row.credit_balance || row.delta_credits || 0)} 积分`;
  if (type === "admin_adjust") return `后台调整 ${formatCreditNumber(row.delta_credits || 0)} 积分`;
  return `${feature || "积分变动"} ${formatCreditNumber(creditTransactionAmount(row, status))} 积分`;
}

function renderCreditUsage(data) {
  const credits = data && data.credits ? data.credits : creditSnapshotFromStatus(state.desktopLicenseStatus);
  write("creditUsageBalance", formatCreditNumber(credits.balance));
  write("creditUsageGrant", formatCreditNumber(credits.grant_monthly));
  write("creditUsageUsed", formatCreditNumber(credits.total_used));
  const list = $("creditUsageList");
  if (!list) return;
  const rows = Array.isArray(data && data.transactions) ? data.transactions : [];
  if (!rows.length) {
    list.textContent = "暂无积分消耗记录。";
    return;
  }
  list.innerHTML = rows.map((row) => {
    const title = escapeHtml(creditTransactionTitle(row));
    const detail = escapeHtml(creditTransactionDetail(row));
    const time = escapeHtml(formatCreditTime(row.updated_at || row.created_at || ""));
    const task = row.task_id ? ` · 任务 ${escapeHtml(row.task_id)}` : "";
    const detailHtml = detail ? `<span>${detail}</span>` : "";
    return `<div class="credit-usage-row"><strong>${title}</strong>${detailHtml}<small>${time}${task}</small></div>`;
  }).join("");
}

async function openCreditUsageDialog() {
  setCreditUsageDialogVisible(true);
  const credits = creditSnapshotFromStatus(state.desktopLicenseStatus);
  write("creditUsageBalance", formatCreditNumber(credits.balance));
  write("creditUsageGrant", formatCreditNumber(credits.grant_monthly));
  write("creditUsageUsed", formatCreditNumber(credits.total_used));
  write("creditUsageList", "正在读取积分记录...");
  try {
    const body = await api("/desktop/license/credits?limit=20");
    state.creditUsage = body;
    renderCreditUsage(body);
    if (body && body.credits && state.desktopLicenseStatus) {
      state.desktopLicenseStatus.credits = body.credits;
      renderCreditBalance(state.desktopLicenseStatus);
    }
  } catch (error) {
    write("creditUsageList", error.message || "积分记录读取失败，请稍后重试。");
  }
}

function renderDesktopLicenseStatus(status) {
  state.desktopLicenseStatus = status || null;
  const allowed = Boolean(status && status.allowed);
  setDesktopLicenseGateVisible(!allowed);
  renderCreditBalance(status);
  const badge = $("taskStatus");
  if (allowed) {
    const customer = status.customer_name ? `已授权：${status.customer_name}` : "授权可用";
    if (badge) badge.textContent = customer;
    writeDesktopLicenseStatus(status.message || "授权校验通过。", "ok");
    return;
  }
  if (badge) badge.textContent = "未激活";
  const message = status && status.message ? status.message : "请先激活软件。";
  const kind = status && status.status === "offline_expired" ? "warn" : "error";
  writeDesktopLicenseStatus(message, kind);
}

async function refreshDesktopLicenseStatus() {
  writeDesktopLicenseStatus("正在校验授权...");
  try {
    const status = await api(`/desktop/license/status?version=${encodeURIComponent(desktopAppVersion())}`);
    renderDesktopLicenseStatus(status);
    return status;
  } catch (error) {
    setDesktopLicenseGateVisible(true);
    writeDesktopLicenseStatus(error.message || "授权服务器暂时不可用，请稍后重试。", "error");
    return null;
  }
}

async function activateDesktopLicense() {
  const licenseKey = value("desktopLicenseKeyInput");
  if (!licenseKey) {
    writeDesktopLicenseStatus("请输入授权码。", "warn");
    return;
  }
  const button = $("desktopLicenseActivateBtn");
  if (button) button.disabled = true;
  writeDesktopLicenseStatus("正在激活，请稍候...");
  try {
    const status = await api("/desktop/license/activate", {
      method: "POST",
      body: JSON.stringify({
        license_key: licenseKey,
        app_version: desktopAppVersion(),
        device_name: "",
      }),
    });
    const input = $("desktopLicenseKeyInput");
    if (input) input.value = "";
    renderDesktopLicenseStatus(status);
  } catch (error) {
    writeDesktopLicenseStatus(error.message || "激活失败，请检查授权码。", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function deactivateDesktopLicense() {
  await api("/desktop/license/deactivate", { method: "POST", body: JSON.stringify({}) });
  setDesktopLicenseGateVisible(true);
  writeDesktopLicenseStatus("已清除本机授权，请重新输入授权码。", "warn");
  const badge = $("taskStatus");
  if (badge) badge.textContent = "未激活";
  renderCreditBalance(null);
  setCreditUsageDialogVisible(false);
}

function navGroupFor(viewName) {
  const groups = {
    "clone-avatar": "projects",
    "digital-humans": "source-video-human",
    "digital-human-detail": "source-video-human",
    "voice-profiles": "projects",
    "references": "source-video-human",
    "script-rewrite": "source-video-human",
    "campaigns": "source-video-human",
    "task-detail": "job-center",
    "results": "job-center",
    "quality-center": "job-center",
    "publish-console": "job-center",
    "trial-feedback": "source-video-human",
  };
  return groups[viewName] || viewName;
}

function switchView(viewName) {
  if (viewName === "create-task") viewName = "source-video-human";
  for (const view of document.querySelectorAll("[data-view]")) {
    view.classList.toggle("active", view.dataset.view === viewName);
  }
  const activeNav = navGroupFor(viewName);
  for (const button of document.querySelectorAll("[data-nav]")) {
    button.classList.toggle("active", button.dataset.nav === activeNav);
  }
  if (viewName === "readiness") safeRun(refreshReadiness);
  if (viewName === "model-center") safeRun(refreshModelCenter);
  if (viewName === "projects") safeRun(refreshProjects);
  if (viewName === "clone-avatar") safeRun(refreshSourceVideoHumans);
  if (viewName === "digital-humans" && state.projectId) safeRun(refreshDigitalHumans);
  if (viewName === "digital-human-detail" && state.digitalHumanId) safeRun(refreshRoleModels);
  if (viewName === "source-video-human") {
    safeRun(refreshSourceVideoHumans);
    safeRun(refreshSourceVideoRunningTaskStatus);
  }
  if (viewName === "references" && state.projectId) safeRun(refreshReferences);
  if (viewName === "script-rewrite" && state.referenceId) safeRun(refreshRewrites);
  if (viewName === "campaigns") safeRun(refreshVideoTemplates);
  if (viewName === "voice-profiles" && state.projectId) safeRun(refreshVoiceProfiles);
  if (viewName === "quality-center") safeRun(refreshQualityDashboard);
  if (viewName === "job-center") safeRun(refreshJobs);
  if (viewName === "publish-console") safeRun(refreshPublishConsole);
  if (viewName === "trial-feedback") safeRun(refreshFeedback);
}

function setDownload(id, href) {
  const link = $(id);
  if (!link) return;
  link.href = href;
  link.classList.remove("disabled");
}

function clearDownloads() {
  for (const id of ["downloadFinal", "downloadJianying", "downloadPublish", "downloadQuality", "downloadAll"]) {
    const link = $(id);
    if (!link) continue;
    link.removeAttribute("href");
    link.classList.add("disabled");
  }
  const preview = $("videoPreview");
  if (preview) preview.removeAttribute("src");
}

function setVoicePreviewSource(src, { objectUrl = false } = {}) {
  const voicePreview = $("voicePreview");
  if (!voicePreview) return null;
  if (state.voicePreviewObjectUrl && state.voicePreviewObjectUrl !== src) {
    URL.revokeObjectURL(state.voicePreviewObjectUrl);
    state.voicePreviewObjectUrl = "";
  }
  if (objectUrl) state.voicePreviewObjectUrl = src;
  voicePreview.src = src;
  voicePreview.load();
  return voicePreview;
}

async function playVoicePreviewSource(src, successMessage, options = {}) {
  const voicePreview = setVoicePreviewSource(src, options);
  if (!voicePreview) return;
  try {
    await voicePreview.play();
    log(successMessage, "ok");
  } catch (_error) {
    log(`${successMessage}，请点击播放器左侧播放按钮试听。`, "ok");
  }
}

function fillSelect(select, rows, idKey, labelKey, emptyLabel) {
  if (!select) return;
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = emptyLabel;
  select.appendChild(empty);
  for (const row of rows) {
    const option = document.createElement("option");
    option.value = row[idKey];
    option.textContent = `${row[labelKey] || row[idKey]} (${row[idKey]})`;
    select.appendChild(option);
  }
}

function renderRows(boxId, rows, idKey, labelKey, emptyLabel, onSelect) {
  const box = $(boxId);
  if (!box) return;
  box.innerHTML = "";
  if (!rows.length) {
    box.className = "list-box empty";
    box.textContent = emptyLabel;
    return;
  }
  box.className = "list-box";
  for (const row of rows) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "list-row";
    const title = document.createElement("strong");
    title.textContent = row[labelKey] || row[idKey];
    const subtitle = document.createElement("span");
    subtitle.textContent = row[idKey];
    item.appendChild(title);
    item.appendChild(subtitle);
    item.onclick = () => onSelect(row);
    box.appendChild(item);
  }
}

function digitalHumanAssetPath(human) {
  const metadata = human.metadata || {};
  const sourceTracking = metadata.source_tracking || {};
  const sourceVideo = metadata.source_video || {};
  return (
    human.selected_avatar_asset ||
    metadata.selected_avatar_asset ||
    sourceTracking.stored_path ||
    sourceVideo.source_video_path ||
    ""
  );
}

function sourceVideoHumanHasVisibleAsset(human) {
  return Boolean(digitalHumanAssetPath(human));
}

function sourceVideoHumanIsEmptyStub(human) {
  const metadata = human && human.metadata ? human.metadata : {};
  if (!human || !human.digital_human_id) return false;
  return (
    !sourceVideoHumanHasVisibleAsset(human) &&
    !human.selected_avatar_asset &&
    !metadata.selected_avatar_asset &&
    !metadata.source_video &&
    !metadata.source_tracking &&
    !metadata.hifly_avatar &&
    !metadata.tavus_replica_id
  );
}

function sourceVideoHistoryRows(allRows) {
  const rows = allRows || [];
  const visible = rows.filter((human) => sourceVideoHumanHasVisibleAsset(human) || human.digital_human_id === state.sourceVideoLastPreparedHumanId);
  const hiddenEmptyCount = rows.filter(sourceVideoHumanIsEmptyStub).length;
  return { visible, hiddenEmptyCount, totalCount: rows.length };
}

function mediaKindFromPath(path) {
  const normalized = String(path || "").split("?")[0].toLowerCase();
  if (/\.(mp4|mov|webm|mkv|avi|m4v)$/.test(normalized)) return "video";
  if (/\.(png|jpg|jpeg|webp|gif|svg)$/.test(normalized)) return "image";
  return "";
}

function previewAvatarUrl(digitalHumanId) {
  return `/digital-humans/${encodeURIComponent(digitalHumanId)}/asset-preview/avatar`;
}

function humanInitials(human) {
  const label = String(human.source_video_picker_label || human.name || human.digital_human_id || "形象").trim();
  return label.slice(0, 2);
}

function appendHumanPreviewPlaceholder(target, human, label = "暂无图片") {
  target.innerHTML = "";
  const badge = document.createElement("span");
  badge.className = "human-preview-placeholder";
  const initials = document.createElement("strong");
  initials.textContent = humanInitials(human);
  const hint = document.createElement("small");
  hint.textContent = label;
  badge.appendChild(initials);
  badge.appendChild(hint);
  target.appendChild(badge);
}

function renderDigitalHumanPreviewCards(boxId, rows, options = {}) {
  const box = $(boxId);
  if (!box) return;
  const idKey = options.idKey || "digital_human_id";
  const labelKey = options.labelKey || "name";
  const emptyLabel = options.emptyLabel || "暂无数字人";
  const onSelect = options.onSelect || (() => {});
  box.innerHTML = "";
  if (!rows.length) {
    box.className = "human-preview-grid empty asset-empty";
    const title = document.createElement("strong");
    title.textContent = emptyLabel;
    const hint = document.createElement("span");
    hint.textContent = "上传或创建后，形象会以图片卡片显示在这里。";
    box.appendChild(title);
    box.appendChild(hint);
    return;
  }
  box.className = "human-preview-grid";
  for (const human of rows) {
    const digitalHumanId = human[idKey];
    const label = human[labelKey] || human.name || digitalHumanId;
    const assetPath = digitalHumanAssetPath(human);
    const mediaKind = mediaKindFromPath(assetPath);
    const card = document.createElement("button");
    card.type = "button";
    card.className = `human-preview-card${digitalHumanId === state.digitalHumanId ? " selected" : ""}`;

    const thumb = document.createElement("span");
    thumb.className = "human-preview-thumb";
    if (mediaKind === "image") {
      const img = document.createElement("img");
      img.src = previewAvatarUrl(digitalHumanId);
      img.alt = `${label}形象预览`;
      img.loading = "lazy";
      img.onerror = () => appendHumanPreviewPlaceholder(thumb, human, "图片不可用");
      thumb.appendChild(img);
    } else if (mediaKind === "video") {
      const video = document.createElement("video");
      video.src = previewAvatarUrl(digitalHumanId);
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.onerror = () => appendHumanPreviewPlaceholder(thumb, human, "视频不可用");
      thumb.appendChild(video);
    } else {
      appendHumanPreviewPlaceholder(thumb, human);
    }

    const title = document.createElement("strong");
    title.textContent = label;
    const subtitle = document.createElement("span");
    subtitle.textContent = digitalHumanId;
    card.appendChild(thumb);
    card.appendChild(title);
    card.appendChild(subtitle);
    card.onclick = () => {
      for (const sibling of box.querySelectorAll(".human-preview-card")) sibling.classList.remove("selected");
      card.classList.add("selected");
      onSelect(human);
      safeRun(() => showDigitalHumanPreview(human));
    };
    box.appendChild(card);
  }
}

async function showDigitalHumanPreview(human) {
  const digitalHumanId = human.digital_human_id;
  if (!digitalHumanId) return;
  state.previewDigitalHumanId = digitalHumanId;
  showModal("digitalHumanPreviewModal", true);
  write("digitalHumanPreviewTitle", human.source_video_picker_label || human.name || "形象预览");
  write("digitalHumanPreviewId", digitalHumanId);
  write("digitalHumanPreviewName", human.name || human.source_video_picker_label || "-");
  const mediaBox = $("digitalHumanPreviewMedia");
  if (mediaBox) {
    mediaBox.innerHTML = "";
    appendHumanPreviewPlaceholder(mediaBox, human, "加载预览中");
  }
  let preview = null;
  try {
    preview = await api(`/digital-humans/${encodeURIComponent(digitalHumanId)}/asset-preview`);
  } catch (error) {
    log(`形象预览加载失败：${error.message || error}`, "error");
  }
  const mediaKind = (preview && preview.avatar_media_type) || mediaKindFromPath(digitalHumanAssetPath(human));
  const mediaUrl = (preview && preview.avatar_url) || (mediaKind ? previewAvatarUrl(digitalHumanId) : "");
  write("digitalHumanPreviewFilename", (preview && preview.avatar_filename) || "未选择素材");
  if (!mediaBox) return;
  mediaBox.innerHTML = "";
  if (mediaKind === "image" && mediaUrl) {
    const img = document.createElement("img");
    img.src = mediaUrl;
    img.alt = `${human.name || digitalHumanId}形象预览`;
    img.onerror = () => appendHumanPreviewPlaceholder(mediaBox, human, "图片不可用");
    mediaBox.appendChild(img);
    return;
  }
  if (mediaKind === "video" && mediaUrl) {
    const video = document.createElement("video");
    video.src = mediaUrl;
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.onerror = () => appendHumanPreviewPlaceholder(mediaBox, human, "视频不可用");
    mediaBox.appendChild(video);
    return;
  }
  appendHumanPreviewPlaceholder(mediaBox, human);
}

async function refreshVideoTemplates() {
  const body = await api("/video-templates");
  state.videoTemplates = body.templates || [];
  fillSelect($("videoTemplateSelect"), state.videoTemplates, "template_id", "name", "选择视频模板");
  fillSelect($("campaignTemplateSelect"), state.videoTemplates, "template_id", "name", "选择视频模板");
  if ($("videoTemplateSelect")) {
    $("videoTemplateSelect").value = state.videoTemplateId || "clean_talking_head";
    if (!$("videoTemplateSelect").value && state.videoTemplates.length) {
      $("videoTemplateSelect").value = state.videoTemplates[0].template_id;
    }
  }
  if ($("campaignTemplateSelect")) $("campaignTemplateSelect").value = state.videoTemplateId || "clean_talking_head";
  previewVideoTemplate();
}

function previewVideoTemplate() {
  const selected = value("videoTemplateSelect") || state.videoTemplateId || "clean_talking_head";
  state.videoTemplateId = selected;
  const template = state.videoTemplates.find((item) => item.template_id === selected);
  if (template) {
    writeJson("templateInfoBox", {
      template_id: template.template_id,
      name: template.name,
      resolution: template.resolution,
      subtitle_style: template.subtitle_style,
      title_style: template.title_style,
      bgm: template.bgm,
      intro: template.intro,
      outro: template.outro,
      safe_area: template.safe_area,
      cover_text: template.cover_text,
    });
  } else {
    write("templateInfoBox", "选择视频模板后在这里预览布局信息。");
  }
}

function populateDigitalHumanProviderSelect() {
  const select = $("digitalHumanProviderSelect");
  if (!select) return;
  const previous = select.value;
  select.innerHTML = "";
  for (const [providerId, config] of Object.entries(digitalHumanProviderFieldMap)) {
    const option = document.createElement("option");
    option.value = providerId;
    option.textContent = config.label;
    select.appendChild(option);
  }
  select.value = previous && digitalHumanProviderFieldMap[previous] ? previous : "hifly";
}

function syncDigitalHumanProviderSelect() {
  const select = $("digitalHumanProviderSelect");
  if (!select) return;
  const selectedModel = value("digitalHumanModelSelect");
  if (selectedModel && digitalHumanProviderFieldMap[selectedModel]) {
    select.value = selectedModel;
  }
}

function statusLabel(status) {
  const labels = {
    green: "可用",
    yellow: "注意",
    red: "缺失",
    disabled: "未启用",
  };
  return labels[status] || status || "未知";
}

function fillModelSelect(selectId, rows, emptyLabel) {
  const select = $(selectId);
  if (!select) return;
  const previous = select.value;
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = emptyLabel;
  select.appendChild(empty);
  for (const row of rows || []) {
    const option = document.createElement("option");
    option.value = row.model_id;
    option.textContent = `${row.label || row.model_id} / ${statusLabel(row.status)}`;
    if (row.description) option.title = row.description;
    select.appendChild(option);
  }
  if (previous) select.value = previous;
}

function setModelSelection(selection) {
  if (!selection) return;
  state.currentModelSelection = selection;
  if ($("voiceModelSelect")) $("voiceModelSelect").value = selection.voice_model || "";
  if ($("digitalHumanModelSelect")) $("digitalHumanModelSelect").value = selection.digital_human_model || "";
  if ($("scriptModelSelect")) $("scriptModelSelect").value = selection.script_model || "";
  if ($("exportModelSelect")) $("exportModelSelect").value = selection.export_model || "";
  if ($("qualityModeSelect")) $("qualityModeSelect").value = selection.quality_mode || "";
}

function modelSelectionPayload() {
  return {
    voice_model: value("voiceModelSelect") || "edge_tts_no_clone",
    digital_human_model: value("digitalHumanModelSelect") || "syncso",
    script_model: value("scriptModelSelect") || "manual_script",
    export_model: value("exportModelSelect") || "mp4_only",
    quality_mode: value("qualityModeSelect") || "preview",
  };
}

function selectedModelSummaries() {
  if (!state.modelCatalog) return [];
  const payload = modelSelectionPayload();
  const groups = [
    ["声音模型", state.modelCatalog.voice_models || [], payload.voice_model],
    ["数字人模型", state.modelCatalog.digital_human_models || [], payload.digital_human_model],
    ["脚本模型", state.modelCatalog.script_models || [], payload.script_model],
    ["导出方式", state.modelCatalog.export_models || [], payload.export_model],
    ["质量模式", state.modelCatalog.quality_modes || [], payload.quality_mode],
  ];
  return groups.map(([name, rows, modelId]) => {
    const row = rows.find((item) => item.model_id === modelId) || {};
    return {
      name,
      model_id: modelId,
      label: row.label || modelId,
      status: statusLabel(row.status),
      missing_items: row.missing_items || [],
      cost_note: row.cost_note || "",
      requires_paid_call: Boolean(row.requires_paid_call),
      description: row.description || "",
    };
  });
}

function renderModelStatus(title, data) {
  const summary = {
    标题: title,
    当前选择: selectedModelSummaries(),
  };
  if (data) {
    summary.总体状态 = statusLabel(data.overall_status);
    summary.缺失配置 = data.missing_items || [];
    summary.提示 = data.warnings || [];
    if (data.selection) summary.保存后的选择 = data.selection;
  }
  writeJson("modelStatusBox", summary);
}

async function refreshModelCenter() {
  const body = await api("/models/catalog");
  state.modelCatalog = body;
  populateDigitalHumanProviderSelect();
  fillModelSelect("voiceModelSelect", body.voice_models || [], "选择声音模型");
  fillModelSelect("digitalHumanModelSelect", body.digital_human_models || [], "选择数字人模型");
  fillModelSelect("scriptModelSelect", body.script_models || [], "选择脚本模型");
  fillModelSelect("exportModelSelect", body.export_models || [], "选择导出方式");
  fillModelSelect("qualityModeSelect", body.quality_modes || [], "选择质量模式");
  setModelSelection(body.selection);
  syncDigitalHumanProviderSelect();
  await loadDigitalHumanProviderConfig();
  if (state.desktopSettings) setObjectStorageFields(state.desktopSettings);
  renderModelStatus("模型列表已刷新。");
  log("模型中心已刷新。", "ok");
}

function selectedDigitalHumanProviderConfig() {
  const providerId = value("digitalHumanProviderSelect") || "hifly";
  return {
    providerId,
    ...(digitalHumanProviderFieldMap[providerId] || digitalHumanProviderFieldMap.hifly),
  };
}

function setDigitalHumanProviderFields(settings) {
  const config = selectedDigitalHumanProviderConfig();
  const baseInput = $("digitalHumanProviderBaseUrl");
  const apiKeyInput = $("digitalHumanProviderApiKey");
  if (baseInput) {
    baseInput.value = config.baseUrlKey ? settings[config.baseUrlKey] || config.defaultBaseUrl : config.defaultBaseUrl;
    baseInput.readOnly = !config.baseUrlKey;
    baseInput.title = config.baseUrlKey ? "" : "该平台使用固定 API 地址。";
  }
  if (apiKeyInput) apiKeyInput.value = "";
  writeJson("digitalHumanProviderConfigStatus", {
    platform: config.label,
    api_address: config.baseUrlKey ? settings[config.baseUrlKey] || config.defaultBaseUrl : config.defaultBaseUrl,
    api_key_configured: Boolean(settings[config.apiKeyKey]),
  });
}

function markDigitalHumanProviderConfigDirty() {
  const config = selectedDigitalHumanProviderConfig();
  writeJson("digitalHumanProviderConfigStatus", {
    platform: config.label,
    api_address: value("digitalHumanProviderBaseUrl") || config.defaultBaseUrl,
    api_key_input: Boolean(value("digitalHumanProviderApiKey")),
    status: "待保存",
    message: "已输入，点击“保存配置”后才会写入并刷新上方模型状态。",
  });
}

async function loadDigitalHumanProviderConfig() {
  const settings = await api("/settings/desktop");
  state.desktopSettings = settings;
  setDigitalHumanProviderFields(settings);
  return settings;
}

function selectedObjectStorageBackend() {
  return value("objectStorageBackendSelect") || "local";
}

function objectStorageStatusFromSettings(settings, message = "当前保存的自动上传配置。") {
  const backend = settings.OBJECT_STORAGE_BACKEND || "local";
  const normalizedBackend = backend.toLowerCase();
  return {
    platform: objectStorageBackendLabels[backend] || backend,
    enabled: !["", "local", "none", "disabled"].includes(normalizedBackend),
    public_base_url_configured: Boolean(settings.OBJECT_STORAGE_PUBLIC_BASE_URL),
    bucket_configured: Boolean(settings.OBJECT_STORAGE_BUCKET),
    endpoint_configured: Boolean(settings.OBJECT_STORAGE_ENDPOINT),
    region_configured: Boolean(settings.OBJECT_STORAGE_REGION),
    access_key_id_configured: Boolean(settings.OBJECT_STORAGE_ACCESS_KEY_ID),
    secret_key_configured: Boolean(settings.OBJECT_STORAGE_SECRET_ACCESS_KEY),
    message,
  };
}

function setObjectStorageFields(settings) {
  if (!settings) return;
  const backend = settings.OBJECT_STORAGE_BACKEND || "local";
  const backendSelect = $("objectStorageBackendSelect");
  if (backendSelect) {
    backendSelect.value = backend;
    if (!backendSelect.value) backendSelect.value = "local";
  }
  const effectiveBackend = selectedObjectStorageBackend();
  if ($("objectStoragePublicBaseUrl")) $("objectStoragePublicBaseUrl").value = settings.OBJECT_STORAGE_PUBLIC_BASE_URL || "";
  if ($("objectStorageBucket")) $("objectStorageBucket").value = settings.OBJECT_STORAGE_BUCKET || "";
  if ($("objectStorageEndpointOrRegion")) {
    $("objectStorageEndpointOrRegion").value =
      effectiveBackend === "tencent_cos" ? settings.OBJECT_STORAGE_REGION || "" : settings.OBJECT_STORAGE_ENDPOINT || "";
  }
  if ($("objectStorageAccessKeyId")) $("objectStorageAccessKeyId").value = "";
  if ($("objectStorageSecretAccessKey")) $("objectStorageSecretAccessKey").value = "";
  writeJson("objectStorageConfigStatus", objectStorageStatusFromSettings(settings));
}

async function loadObjectStorageConfig() {
  const settings = state.desktopSettings || (await api("/settings/desktop"));
  state.desktopSettings = settings;
  setObjectStorageFields(settings);
  return settings;
}

function objectStorageSettingsPayload(current) {
  const backend = selectedObjectStorageBackend();
  const endpointOrRegion = value("objectStorageEndpointOrRegion");
  const payload = {
    ...current,
    OBJECT_STORAGE_BACKEND: backend,
    OBJECT_STORAGE_PUBLIC_BASE_URL: value("objectStoragePublicBaseUrl"),
    OBJECT_STORAGE_BUCKET: value("objectStorageBucket"),
    OBJECT_STORAGE_ACCESS_KEY_ID: value("objectStorageAccessKeyId") || current.OBJECT_STORAGE_ACCESS_KEY_ID || "",
    OBJECT_STORAGE_SECRET_ACCESS_KEY: value("objectStorageSecretAccessKey") || current.OBJECT_STORAGE_SECRET_ACCESS_KEY || "",
    OBJECT_STORAGE_PREFIX: current.OBJECT_STORAGE_PREFIX || "aivo",
    OBJECT_STORAGE_ROOT: current.OBJECT_STORAGE_ROOT || "storage/objects",
  };
  if (backend === "tencent_cos") {
    payload.OBJECT_STORAGE_REGION = endpointOrRegion;
    payload.OBJECT_STORAGE_ENDPOINT = current.OBJECT_STORAGE_ENDPOINT || "";
  } else {
    payload.OBJECT_STORAGE_ENDPOINT = endpointOrRegion;
    payload.OBJECT_STORAGE_REGION = current.OBJECT_STORAGE_REGION || "";
  }
  return payload;
}

function markObjectStorageConfigDirty() {
  const backend = selectedObjectStorageBackend();
  writeJson("objectStorageConfigStatus", {
    platform: objectStorageBackendLabels[backend] || backend,
    public_base_url_input: Boolean(value("objectStoragePublicBaseUrl")),
    bucket_input: Boolean(value("objectStorageBucket")),
    endpoint_or_region_input: Boolean(value("objectStorageEndpointOrRegion")),
    access_key_id_input: Boolean(value("objectStorageAccessKeyId")),
    secret_key_input: Boolean(value("objectStorageSecretAccessKey")),
    status: "待保存",
    message: "已输入，点击“保存自动上传”后才会写入。也可以先点击“检查自动上传”。",
  });
}

async function saveObjectStorageConfig() {
  const current = state.desktopSettings || (await api("/settings/desktop"));
  const payload = objectStorageSettingsPayload(current);
  const saved = await api("/settings/desktop", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.desktopSettings = saved;
  setObjectStorageFields(saved);
  writeJson("objectStorageConfigStatus", {
    saved: true,
    ...objectStorageStatusFromSettings(saved, "已保存。源视频创建声音时会自动使用该对象存储上传 clean_voice_sample.wav。"),
  });
  log("对象存储自动上传配置已保存。", "ok");
}

async function checkObjectStorageConfig() {
  const current = state.desktopSettings || (await api("/settings/desktop"));
  const payload = objectStorageSettingsPayload(current);
  const body = await api("/settings/desktop/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const checks = (body.checks || []).filter((item) => String(item.name || "").startsWith("OBJECT_STORAGE"));
  const hasRed = checks.some((item) => item.status === "red");
  writeJson("objectStorageConfigStatus", {
    overall_status: hasRed ? "red" : "green",
    checks,
  });
  log(`对象存储自动上传检查：${hasRed ? "需要补配置" : "配置可用"}`, hasRed ? "error" : "ok");
}

async function saveDigitalHumanProviderConfig() {
  const config = selectedDigitalHumanProviderConfig();
  const current = state.desktopSettings || (await api("/settings/desktop"));
  const previousSelection = modelSelectionPayload();
  const apiKeyInput = value("digitalHumanProviderApiKey");
  const payload = { ...current };
  if (config.baseUrlKey) payload[config.baseUrlKey] = value("digitalHumanProviderBaseUrl") || config.defaultBaseUrl;
  payload[config.apiKeyKey] = apiKeyInput || current[config.apiKeyKey] || "";
  const saved = await api("/settings/desktop", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.desktopSettings = saved;
  if ($("digitalHumanProviderApiKey")) $("digitalHumanProviderApiKey").value = "";
  await refreshModelCenter();
  setModelSelection(previousSelection);
  writeJson("digitalHumanProviderConfigStatus", {
    saved: true,
    platform: config.label,
    api_address: config.baseUrlKey ? saved[config.baseUrlKey] || config.defaultBaseUrl : config.defaultBaseUrl,
    api_key_configured: Boolean(saved[config.apiKeyKey]),
    selected_model_unchanged: previousSelection.digital_human_model,
  });
  log(`${config.label} 配置已保存，模型列表已刷新。`, "ok");
}

async function checkDigitalHumanProviderConfig() {
  const previousSelection = modelSelectionPayload();
  await refreshModelCenter();
  setModelSelection(previousSelection);
  const rows = (state.modelCatalog && state.modelCatalog.digital_human_models) || [];
  const selected = rows.find((item) => item.model_id === previousSelection.digital_human_model) || {};
  const body = {
    selected_model: previousSelection.digital_human_model,
    label: selected.label || previousSelection.digital_human_model,
    status: statusLabel(selected.status),
    missing_items: selected.missing_items || [],
    message: "这里按平台、API 地址和 API Key 做简化检测；真实付费调用前仍可用上方一键校验做完整检查。",
  };
  writeJson("digitalHumanProviderConfigStatus", body);
  renderModelStatus("当前数字人模型检测完成。");
  log(`数字人模型检测：${body.status}`, selected.status === "red" ? "error" : "ok");
}

async function loadModelSelection() {
  if (!state.modelCatalog) await refreshModelCenter();
  const body = await api("/models/selection");
  setModelSelection(body.selection);
  renderModelStatus("已加载当前模型选择。", body);
  log("当前模型选择已加载。", "ok");
}

async function saveModelSelection() {
  const body = await api("/models/selection", {
    method: "PUT",
    body: JSON.stringify(modelSelectionPayload()),
  });
  setModelSelection(body.selection);
  renderModelStatus("模型选择已保存。", body);
  log("模型选择已保存。", "ok");
}

async function validateModelSelection() {
  const body = await api("/models/selection/validate", {
    method: "POST",
    body: JSON.stringify(modelSelectionPayload()),
  });
  renderModelStatus("模型选择校验完成。", body);
  log(`模型校验结果：${statusLabel(body.overall_status)}`, body.overall_status === "red" ? "error" : "ok");
}

async function applyModelPreset() {
  const presetId = value("modelPresetSelect") || "hifly_one_video";
  const body = await api("/models/presets/apply", {
    method: "POST",
    body: JSON.stringify({ preset_id: presetId }),
  });
  await refreshModelCenter();
  setModelSelection(body.selection);
  renderModelStatus("一键方案已套用。", body);
  log(`一键方案已套用：${presetId}`, "ok");
}

function showModal(id, show = true) {
  const modal = $(id);
  if (modal) modal.classList.toggle("hidden", !show);
}

function selectedLlmPlatform() {
  if (!state.llmPlatforms) return null;
  return (state.llmPlatforms.platforms || []).find((item) => item.id === state.selectedLlmPlatformId) || null;
}

function enableSingleLlmPlatform(platformId) {
  if (!state.llmPlatforms) return;
  for (const platform of state.llmPlatforms.platforms || []) {
    platform.enabled = platform.id === platformId;
  }
  state.llmPlatforms.activePlatformId = platformId;
}

function enableSingleLlmModelSelection(platformId, modelId) {
  if (!state.llmPlatforms) return;
  enableSingleLlmPlatform(platformId);
  state.llmPlatforms.activeModelId = modelId;
  for (const platform of state.llmPlatforms.platforms || []) {
    for (const model of platform.models || []) {
      model.enabled = platform.id === platformId && model.id === modelId;
    }
  }
}

async function loadLlmPlatforms() {
  const body = await api("/llm/platforms");
  state.llmPlatforms = body;
  const platforms = body.platforms || [];
  const selectedExists = platforms.some((item) => item.id === state.selectedLlmPlatformId);
  if (!selectedExists) {
    state.selectedLlmPlatformId = body.activePlatformId || (platforms[0] && platforms[0].id) || "";
  }
  renderLlmPlatformList();
  renderLlmPlatformDetail();
}

async function ensureLlmPlatforms() {
  if (!state.llmPlatforms) await loadLlmPlatforms();
  if (!state.llmPlatforms) throw new Error("大模型平台配置尚未加载。");
  return state.llmPlatforms;
}

async function openLlmSettings() {
  showModal("llmSettingsModal", true);
  await loadLlmPlatforms();
}

function renderLlmPlatformList() {
  const box = $("llmPlatformList");
  if (!box || !state.llmPlatforms) return;
  const query = value("llmPlatformSearch").toLowerCase();
  const platforms = (state.llmPlatforms.platforms || []).filter((platform) => {
    if (!query) return true;
    return `${platform.name || ""} ${platform.id || ""}`.toLowerCase().includes(query);
  });
  box.innerHTML = "";
  if (!platforms.length) {
    box.className = "llm-platform-list empty";
    box.textContent = "没有匹配的平台。";
    return;
  }
  box.className = "llm-platform-list";
  for (const platform of platforms) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `llm-platform-item${platform.id === state.selectedLlmPlatformId ? " active" : ""}`;

    const icon = document.createElement("img");
    icon.className = "llm-platform-icon";
    icon.src = platform.icon || "/provider-icons/custom.svg";
    icon.alt = "";
    icon.loading = "lazy";

    const text = document.createElement("span");
    text.className = "llm-platform-text";
    const title = document.createElement("strong");
    title.textContent = platform.name || platform.id;
    const subtitle = document.createElement("span");
    subtitle.textContent = platform.hasApiKey ? "已配置 API Key" : "未配置 API Key";
    text.append(title, subtitle);

    item.append(icon, text);
    item.onclick = () => {
      updateSelectedLlmPlatformFromInputs();
      state.selectedLlmPlatformId = platform.id;
      renderLlmPlatformList();
      renderLlmPlatformDetail();
    };
    box.appendChild(item);
  }
}

function renderLlmPlatformDetail() {
  const platform = selectedLlmPlatform();
  if (!platform) {
    write("llmPlatformName", "未选择平台");
    write("llmPlatformStatus", "未配置");
    write("llmApiKeyStatus", "未检查");
    const icon = $("llmPlatformIcon");
    if (icon) {
      icon.removeAttribute("src");
      icon.hidden = true;
    }
    const enabled = $("llmPlatformEnabled");
    const apiKey = $("llmApiKey");
    const baseUrl = $("llmBaseUrl");
    if (enabled) enabled.checked = false;
    if (apiKey) apiKey.value = "";
    if (baseUrl) baseUrl.value = "";
    renderLlmModelList({ models: [] });
    return;
  }

  write("llmPlatformName", platform.name || platform.id);
  write("llmPlatformStatus", platform.enabled ? "已启用" : "未启用");
  const detailIcon = $("llmPlatformIcon");
  if (detailIcon) {
    detailIcon.src = platform.icon || "/provider-icons/custom.svg";
    detailIcon.hidden = false;
  }
  const enabled = $("llmPlatformEnabled");
  const apiKey = $("llmApiKey");
  const baseUrl = $("llmBaseUrl");
  if (enabled) enabled.checked = Boolean(platform.enabled);
  if (enabled) {
    enabled.onchange = () => {
      if (enabled.checked) {
        enableSingleLlmPlatform(platform.id);
        write("llmPlatformStatus", "已启用");
        writeJson("llmSettingsStatus", {
          status: "selected",
          message: "已切换为唯一启用平台，保存后生效。",
          activePlatformId: platform.id,
        });
      } else {
        enabled.checked = true;
        platform.enabled = true;
        writeJson("llmSettingsStatus", {
          status: "blocked",
          message: "至少需要保留一个文案大模型平台启用。",
          activePlatformId: platform.id,
        });
      }
      renderLlmPlatformList();
    };
  }
  if (apiKey) apiKey.value = "";
  if (baseUrl) baseUrl.value = platform.baseUrl || "";
  write("llmApiKeyStatus", platform.hasApiKey ? `已配置 ${platform.apiKeyPreview || ""}` : "未配置 API Key");
  renderLlmModelList(platform);
}

function updateSelectedLlmPlatformFromInputs() {
  const platform = selectedLlmPlatform();
  if (!platform) return null;
  const enabled = $("llmPlatformEnabled");
  if (enabled && enabled.checked) enableSingleLlmPlatform(platform.id);
  platform.baseUrl = value("llmBaseUrl");
  const apiKey = value("llmApiKey");
  if (apiKey) platform.apiKey = apiKey;
  return platform;
}

function renderLlmModelList(platform) {
  const box = $("llmModelList");
  if (!box) return;
  const models = platform && platform.models ? platform.models : [];
  box.innerHTML = "";
  if (!models.length) {
    box.className = "llm-model-list empty";
    box.textContent = "暂无模型，可点击添加模型或刷新模型。";
    return;
  }

  box.className = "llm-model-list";
  const groups = new Map();
  for (const model of models) {
    const group = model.group || "Custom";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(model);
  }

  for (const [group, rows] of groups.entries()) {
    const section = document.createElement("section");
    section.className = "llm-model-group";
    const title = document.createElement("div");
    title.className = "llm-model-group-title";
    title.textContent = group;
    section.appendChild(title);

    for (const model of rows) {
      const row = document.createElement("div");
      const isActive =
        state.llmPlatforms &&
        state.llmPlatforms.activePlatformId === platform.id &&
        state.llmPlatforms.activeModelId === model.id;
      row.className = `llm-model-row${isActive ? " active" : ""}`;

      const label = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = model.name || model.id;
      const id = document.createElement("span");
      id.className = "field-hint";
      id.textContent = model.id;
      label.append(name, id);

      const actions = document.createElement("div");
      actions.className = "model-row-actions";

      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = isActive ? "当前启用" : "启用";
      toggle.onclick = () => {
        enableSingleLlmModelSelection(platform.id, model.id);
        writeJson("llmSettingsStatus", {
          status: "selected",
          message: "全局只启用这一个文案模型，保存后生效。",
          activePlatformId: platform.id,
          activeModelId: model.id,
        });
        renderLlmPlatformList();
        renderLlmModelList(platform);
      };

      const select = document.createElement("button");
      select.type = "button";
      select.textContent = isActive ? "默认模型" : "设为默认";
      select.onclick = () => safeRun(() => selectLlmModel(platform.id, model.id));

      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "删除";
      remove.onclick = () => {
        platform.models = (platform.models || []).filter((item) => item.id !== model.id);
        renderLlmModelList(platform);
      };

      actions.append(toggle, select, remove);
      row.append(label, actions);
      section.appendChild(row);
    }

    box.appendChild(section);
  }
}

async function saveLlmPlatforms() {
  await ensureLlmPlatforms();
  updateSelectedLlmPlatformFromInputs();
  const body = await api("/llm/platforms", {
    method: "PUT",
    body: JSON.stringify(state.llmPlatforms),
  });
  state.llmPlatforms = body;
  const platforms = body.platforms || [];
  if (!platforms.some((item) => item.id === state.selectedLlmPlatformId)) {
    state.selectedLlmPlatformId = body.activePlatformId || (platforms[0] && platforms[0].id) || "";
  }
  renderLlmPlatformList();
  renderLlmPlatformDetail();
  writeJson("llmSettingsStatus", {
    status: "saved",
    activePlatformId: body.activePlatformId,
    activeModelId: body.activeModelId,
  });
  log("大模型平台配置已保存。", "ok");
  return body;
}

async function checkLlmPlatform() {
  await ensureLlmPlatforms();
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const platform = selectedLlmPlatform();
  if (!platform) throw new Error("请先选择平台。");
  const body = await api(`/llm/platforms/${encodeURIComponent(platform.id)}/check`, {
    method: "POST",
    body: "{}",
  });
  writeJson("llmSettingsStatus", body);
  write("llmApiKeyStatus", body.message || "检查完成。");
}

async function refreshLlmModels() {
  await ensureLlmPlatforms();
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const platform = selectedLlmPlatform();
  if (!platform) throw new Error("请先选择平台。");
  const body = await api(`/llm/platforms/${encodeURIComponent(platform.id)}/models/refresh`, {
    method: "POST",
    body: "{}",
  });
  writeJson("llmSettingsStatus", body);
  await loadLlmPlatforms();
}

function addLlmModel() {
  const platform = updateSelectedLlmPlatformFromInputs();
  if (!platform) throw new Error("请先选择平台。");
  const modelId = window.prompt("请输入模型 ID，例如 gpt-4o-mini");
  if (!modelId || !modelId.trim()) return;
  const id = modelId.trim();
  platform.models = platform.models || [];
  if (platform.models.some((item) => item.id === id)) {
    throw new Error("这个模型 ID 已存在。");
  }
  platform.models.push({ id, name: id, group: "Manual", enabled: false });
  renderLlmModelList(platform);
}

async function selectLlmModel(platformId, modelId) {
  await ensureLlmPlatforms();
  updateSelectedLlmPlatformFromInputs();
  await saveLlmPlatforms();
  const body = await api("/llm/selection", {
    method: "PUT",
    body: JSON.stringify({ platformId, modelId }),
  });
  state.llmPlatforms = body;
  state.selectedLlmPlatformId = platformId;
  renderLlmPlatformList();
  renderLlmPlatformDetail();
  writeJson("llmSettingsStatus", {
    status: "selected",
    activePlatformId: body.activePlatformId,
    activeModelId: body.activeModelId,
  });
  log(`已设置默认大模型：${platformId}/${modelId}`, "ok");
}

async function openLocalLlmModelModal() {
  showModal("localLlmModelModal", true);
  if (!state.llmPlatforms) await loadLlmPlatforms();
  renderLocalLlmModelList();
}

function renderLocalLlmModelList() {
  const rows = (state.llmPlatforms && state.llmPlatforms.localModels) || [];
  renderRows("localLlmModelList", rows, "id", "name", "暂无本地模型", () => {});
}

async function saveLocalLlmModel() {
  const enabled = $("localLlmEnabled");
  const payload = {
    id: "",
    name: value("localLlmName"),
    path: value("localLlmPath"),
    type: value("localLlmType") || "local_path",
    notes: value("localLlmNotes"),
    enabled: enabled ? Boolean(enabled.checked) : true,
  };
  if (!payload.name || !payload.path) throw new Error("请填写本地模型名称和路径。");
  const created = await api("/llm/local-models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadLlmPlatforms();
  renderLocalLlmModelList();
  writeJson("llmSettingsStatus", { localModelCreated: created });
  log(`本地模型已添加：${created.name}`, "ok");
}

function syncCurrentIds() {
  state.projectId = state.projectId || value("projectId") || "project_demo";
  write("dashboardProject", state.projectId || "-");
  write("dashboardHuman", state.digitalHumanId || "-");
  write("dashboardVoice", state.voiceProfileId || "-");
  write("dashboardRoleModel", state.roleModelId || "-");
  write("dashboardReference", state.referenceId || "-");
  write("dashboardTask", state.taskId || "-");
  write("humanId", state.digitalHumanId || "-");
  write("voiceId", state.voiceProfileId || "-");
  write("roleModelId", state.roleModelId || "-");
  write("taskId", state.taskId || "-");
  if (state.taskId && $("currentTaskLookupId")) $("currentTaskLookupId").value = state.taskId;
}

function requireProject() {
  state.projectId = value("projectId") || state.projectId;
  if (!state.projectId) throw new Error("请先创建或选择项目。");
}

function requireHuman() {
  if (!state.digitalHumanId) throw new Error("请先创建或选择数字人。");
}

function requireVoice() {
  if (!state.voiceProfileId) throw new Error("请先创建或选择声音。");
}

function requireTask() {
  if (!state.taskId) throw new Error("请先创建视频任务。");
}

async function refreshProjects() {
  const body = await api("/projects");
  const projects = body.projects || [];
  fillSelect($("projectSelect"), projects, "project_id", "name", "选择已有项目");
  renderRows("projectList", projects, "project_id", "name", "暂无项目", (project) => {
    $("projectSelect").value = project.project_id;
    $("projectId").value = project.project_id;
    safeRun(selectProject);
  });
  if (state.projectId && $("projectSelect")) $("projectSelect").value = state.projectId;
  syncCurrentIds();
}

async function createProject() {
  const projectId = value("projectId") || "project_demo";
  const body = await api("/projects", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      name: value("projectName") || projectId,
      metadata: {},
    }),
  });
  state.projectId = body.project_id;
  state.digitalHumanId = "";
  state.voiceProfileId = "";
  state.roleModelId = "";
  state.referenceId = "";
  state.rewriteId = "";
  state.selectedRewriteScript = null;
  state.taskId = "";
  $("projectId").value = state.projectId;
  clearDownloads();
  await refreshProjects();
  if ($("projectSelect")) $("projectSelect").value = state.projectId;
  syncCurrentIds();
  log(`项目已创建：${state.projectId}`, "ok");
}

async function selectProject() {
  const selected = value("projectSelect") || value("projectId");
  if (!selected) throw new Error("请选择或填写项目 ID。");
  state.projectId = selected;
  state.digitalHumanId = "";
  state.voiceProfileId = "";
  state.roleModelId = "";
  state.referenceId = "";
  state.rewriteId = "";
  state.selectedRewriteScript = null;
  state.taskId = "";
  $("projectId").value = selected;
  clearDownloads();
  await refreshDigitalHumans();
  syncCurrentIds();
  log(`已选择项目：${state.projectId}`, "ok");
}

async function refreshDigitalHumans() {
  requireProject();
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans`);
  const humans = body || [];
  fillSelect($("humanSelect"), humans, "digital_human_id", "name", "选择已有数字人");
  renderDigitalHumanPreviewCards("humanList", humans, {
    emptyLabel: "暂无数字人",
    onSelect: (human) => {
      $("humanSelect").value = human.digital_human_id;
      safeRun(selectDigitalHuman);
    },
  });
  if (state.digitalHumanId && $("humanSelect")) $("humanSelect").value = state.digitalHumanId;
  syncCurrentIds();
}

async function createDigitalHuman() {
  requireProject();
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans`, {
    method: "POST",
    body: JSON.stringify({
      name: value("humanName") || "合成 IP 主播",
      avatar_source_type: "generated",
      avatar_style: { style: "studio", prompt: value("avatarPrompt") || "合成数字人主播" },
    }),
  });
  state.digitalHumanId = body.digital_human_id;
  state.voiceProfileId = "";
  state.roleModelId = "";
  state.taskId = "";
  clearDownloads();
  await refreshDigitalHumans();
  if ($("humanSelect")) $("humanSelect").value = state.digitalHumanId;
  await refreshVoiceProfiles();
  await refreshRoleModels();
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`数字人已创建：${state.digitalHumanId}`, "ok");
}

async function uploadPersonalDigitalHuman() {
  requireProject();
  const fileInput = $("personalHumanFile");
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;
  if (!file) throw new Error("请先选择客户的数字人图片或视频。");
  const contentBase64 = await readFileAsBase64(file);
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans/upload`, {
    method: "POST",
    body: JSON.stringify({
      name: value("personalHumanName") || value("humanName") || "客户个人数字人",
      source_type: "uploaded_reference",
      filename: file.name || "personal_avatar",
      content_type: file.type || "application/octet-stream",
      content_base64: contentBase64,
      tavus_replica_id: value("personalHumanTavusReplicaId"),
    }),
  });
  state.digitalHumanId = body.digital_human_id;
  state.voiceProfileId = "";
  state.roleModelId = "";
  state.taskId = "";
  clearDownloads();
  await refreshDigitalHumans();
  if ($("humanSelect")) $("humanSelect").value = state.digitalHumanId;
  await refreshVoiceProfiles();
  await refreshRoleModels();
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`客户个人数字人已上传并创建：${state.digitalHumanId}`, "ok");
}

async function selectDigitalHuman() {
  const selected = value("humanSelect");
  if (!selected) throw new Error("请先选择数字人。");
  state.digitalHumanId = selected;
  state.voiceProfileId = "";
  state.roleModelId = "";
  state.taskId = "";
  clearDownloads();
  await refreshVoiceProfiles();
  await refreshRoleModels();
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`已选择数字人：${selected}`, "ok");
}

async function refreshSourceVideoHumans() {
  state.projectId = value("sourceVideoProject") || state.projectId || value("projectId") || "project_demo";
  if ($("sourceVideoProject")) $("sourceVideoProject").value = state.projectId;
  if ($("projectId")) $("projectId").value = state.projectId;
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans`);
  const humans = body || [];
  const projectVoices = await loadProjectVoiceProfiles();
  const allHumanRows = buildSourceVideoHumanPickerRows(humans, projectVoices);
  const pickerInfo = sourceVideoPickerSelectionRows(allHumanRows);
  const pickerHumans = pickerInfo.rows;
  state.sourceVideoHumanPickerInfo = pickerInfo;
  state.sourceVideoHumanRows = allHumanRows;
  state.sourceVideoHumanPickerRows = pickerHumans;
  fillSelect(
    $("sourceVideoHumanSelect"),
    pickerHumans,
    "digital_human_id",
    "source_video_picker_label",
    pickerHumans.length ? "选择数字人" : "暂无可制作形象"
  );
  const hasCurrent = pickerHumans.some((human) => human.digital_human_id === state.digitalHumanId);
  if (state.digitalHumanId && hasCurrent && $("sourceVideoHumanSelect")) $("sourceVideoHumanSelect").value = state.digitalHumanId;
  const hasCurrentInProject = (humans || []).some((human) => human.digital_human_id === state.digitalHumanId);
  if (state.digitalHumanId && !hasCurrentInProject) {
    state.digitalHumanId = "";
    state.voiceProfileId = "";
  } else if (
    sourceVideoOnlyReadyEnabled() &&
    state.digitalHumanId &&
    !hasCurrent &&
    !state.sourceVideoProfilePreparing &&
    state.digitalHumanId !== state.sourceVideoLastPreparedHumanId
  ) {
    state.digitalHumanId = "";
    state.voiceProfileId = "";
    if ($("sourceVideoHumanSelect")) $("sourceVideoHumanSelect").value = "";
  }
  if (sourceVideoOnlyReadyEnabled() && !pickerHumans.length && (humans || []).length) {
    showAgentCardStatus("av", "暂无可制作形象。请先在资产管理完成形象/声音配置，或点击“全部”查看历史形象。", "warn");
  } else if (sourceVideoOnlyReadyEnabled() && pickerHumans.length) {
    showAgentCardStatus("av", `已按标准显示 ${pickerHumans.length} 个可制作形象。`, "ok");
  } else if (!sourceVideoOnlyReadyEnabled()) {
    showAgentCardStatus("av", `正在显示全部历史形象，共 ${pickerInfo.totalCount || pickerHumans.length} 个；未完成形象会标注状态。`, "warn");
  }
  if (!value("sourceVideoHumanSelect")) {
    const latest = await findLatestSourceVideoHumanWithVoice(pickerHumans.filter(sourceVideoHumanCanRender), projectVoices);
    if (latest && $("sourceVideoHumanSelect")) {
      state.digitalHumanId = latest.human.digital_human_id;
      state.voiceProfileId = latest.voice.voice_profile_id;
      $("sourceVideoHumanSelect").value = state.digitalHumanId;
    }
  }
  const historyInfo = sourceVideoHistoryRows(allHumanRows);
  write(
    "cloneAvatarHistorySummary",
    historyInfo.hiddenEmptyCount
      ? `已隐藏 ${historyInfo.hiddenEmptyCount} 个空形象。这里只显示有图片/视频素材的形象。`
      : `共 ${historyInfo.visible.length} 个有素材形象。`,
  );
  renderDigitalHumanPreviewCards("cloneAvatarHistoryList", historyInfo.visible, {
    labelKey: "source_video_picker_label",
    emptyLabel: "暂无有素材的历史形象",
    onSelect: (human) => {
      state.digitalHumanId = human.digital_human_id;
      state.voiceProfileId = human.voice_profile_id || state.voiceProfileId || "";
      if ($("sourceVideoHumanSelect")) $("sourceVideoHumanSelect").value = human.digital_human_id;
      safeRun(loadSourceVideoAssetPreview);
      syncCurrentIds();
      log(`已选择形象：${human.name || human.digital_human_id}`, "ok");
    },
  });
  await refreshSourceVideoVoices();
  await loadSourceVideoAssetPreview();
  await refreshSourceVideoRunningTaskStatus();
  updateSourceVideoHumanFilterControls();
  syncCurrentIds();
}

function sourceVideoOnlyReadyEnabled() {
  const checkbox = $("sourceVideoOnlyReadyHumans");
  return !checkbox || checkbox.checked;
}

function decorateSourceVideoHuman(human) {
  const metadata = human.metadata || {};
  const labelParts = [];
  if (metadata.hidden_from_source_video) labelParts.push("已隐藏");
  if (!metadata.source_video) labelParts.push("未上传源视频");
  const suffix = labelParts.length ? `（${labelParts.join("、")}）` : "";
  return {
    ...human,
    source_video_picker_label: `${human.name || human.digital_human_id}${suffix}`,
  };
}

function decorateSourceVideoVoice(voice) {
  const metadata = voice && voice.metadata && typeof voice.metadata === "object" ? voice.metadata : {};
  if (metadata.source === "default_preset_voice_asset") {
    return {
      ...voice,
      source_video_voice_label: `${voice.name || voice.voice_profile_id}（系统预设）`,
    };
  }
  const ownerName = voice.owner_digital_human_name || voice.owner_digital_human_id || voice.digital_human_id || "";
  const suffix = ownerName ? `（来自 ${ownerName}）` : "";
  return {
    ...voice,
    source_video_voice_label: `${voice.name || voice.voice_profile_id}${suffix}`,
  };
}

async function loadProjectVoiceProfiles(options = {}) {
  state.projectId = value("sourceVideoProject") || state.projectId || value("projectId") || "project_demo";
  const endpoint = `/projects/${encodeURIComponent(state.projectId)}/voice-profiles`;
  const query = options.visibleAssetsOnly === false ? "" : "?visible_assets_only=true";
  const voices = await api(`${endpoint}${query}`);
  const rows = (voices || []).map(decorateSourceVideoVoice);
  state.sourceVideoAllVoiceRows = rows;
  state.sourceVideoVoiceRows = rows;
  return rows;
}

function selectedVoiceRow(voiceProfileId = state.voiceProfileId || value("voiceSelect")) {
  const rows = [
    ...(state.voiceProfileRows || []),
    ...(state.sourceVideoAllVoiceRows || []),
    ...(state.sourceVideoVoiceRows || []),
  ];
  return rows.find((voice) => voice.voice_profile_id === voiceProfileId) || null;
}

function voiceOwnerDigitalHumanId(voice) {
  const metadata = voice && voice.metadata ? voice.metadata : {};
  return (
    (voice && (voice.owner_digital_human_id || voice.digital_human_id)) ||
    metadata.owner_digital_human_id ||
    metadata.digital_human_id ||
    ""
  );
}

function selectedVoiceOwnerDigitalHumanId(voice = null) {
  const row = voice || selectedVoiceRow();
  return (
    voiceOwnerDigitalHumanId(row) ||
    state.digitalHumanId ||
    value("humanSelect") ||
    value("sourceVideoHumanSelect")
  );
}

function isProviderTaskReady(providerMetadata, idKeys = []) {
  if (!providerMetadata || typeof providerMetadata !== "object") return false;
  for (const key of idKeys) {
    if (providerMetadata[key]) return true;
  }
  const status = String(providerMetadata.status || providerMetadata.state || "").trim().toLowerCase();
  return ["3", "done", "success", "completed", "ready"].includes(status);
}

function sourceVideoHumanReadiness(human, voices = []) {
  const metadata = human && human.metadata ? human.metadata : {};
  const hiflyAvatar = metadata.hifly_avatar || {};
  const hiflyVoice = metadata.hifly_voice || {};
  const hasSourceVideo = Boolean(metadata.source_video);
  const hasAvatar =
    hasSourceVideo &&
    (!metadata.hifly_avatar ||
      isProviderTaskReady(hiflyAvatar, ["avatar_id", "avatarId", "avatar", "provider_avatar_id"]));
  const hasVoice =
    Boolean(human && human.voice_profile_id) ||
    isProviderTaskReady(hiflyVoice, ["voice_id", "voiceId", "voice", "provider_voice_id"]) ||
    Boolean(
      (voices || []).some((voice) => {
        const owner = voiceOwnerDigitalHumanId(voice);
        return owner && human && owner === human.digital_human_id;
      })
    );
  return {
    hasSourceVideo,
    hasAvatar,
    hasVoice,
    statusLabel: !hasSourceVideo ? "未上传源视频" : !hasAvatar ? "制作中" : !hasVoice ? "待克隆声音" : "",
  };
}

function buildSourceVideoHumanPickerRows(humans, voices = []) {
  const rows = [];
  for (const human of humans || []) {
    if (!human || !human.digital_human_id) continue;
    const metadata = human.metadata || {};
    const readiness = sourceVideoHumanReadiness(human, voices);
    const labelParts = [];
    if (metadata.hidden_from_source_video) labelParts.push("已隐藏");
    if (readiness.statusLabel) labelParts.push(readiness.statusLabel);
    const labelledHuman = decorateSourceVideoHuman(human);
    if (labelParts.length) {
      labelledHuman.source_video_picker_label = `${human.name || human.digital_human_id}（${labelParts.join("、")}）`;
    }
    rows.push({
      ...labelledHuman,
      source_video_readiness: readiness,
    });
  }
  return rows;
}

function sourceVideoHumanCanRender(human) {
  const metadata = human.metadata || {};
  const readiness = human.source_video_readiness || sourceVideoHumanReadiness(human, state.sourceVideoVoiceRows || []);
  // 声音缺失不隐藏形象；声音是项目级资产，制作时可以单独选择或稍后克隆。
  return (
    !metadata.hidden_from_source_video &&
    readiness.hasSourceVideo &&
    readiness.hasAvatar
  );
}

function sourceVideoPickerSelectionRows(allRows) {
  const rows = allRows || [];
  if (!sourceVideoOnlyReadyEnabled()) {
    return { rows, readyCount: rows.filter(sourceVideoHumanCanRender).length, totalCount: rows.length, filterMode: "all" };
  }
  const readyRows = rows.filter(sourceVideoHumanCanRender);
  return { rows: readyRows, readyCount: readyRows.length, totalCount: rows.length, filterMode: "ready" };
}

async function filterSourceVideoHumans(humans, projectVoices = null) {
  const voices = projectVoices || (await loadProjectVoiceProfiles());
  const allRows = buildSourceVideoHumanPickerRows(humans, voices);
  const selection = sourceVideoPickerSelectionRows(allRows);
  state.sourceVideoHumanPickerInfo = selection;
  return selection.rows;
}

async function findLatestSourceVideoHumanWithVoice(humans, projectVoices = null) {
  const voices = projectVoices || (await loadProjectVoiceProfiles());
  if (!voices || !voices.length) return null;
  const candidates = [...(humans || [])].reverse();
  for (const human of candidates) {
    if (!human || !human.digital_human_id) continue;
    const metadata = human.metadata || {};
    if (metadata.hidden_from_source_video) continue;
    if (!metadata.source_video) continue;
    const matchingVoices = voices.filter((voice) => voiceOwnerDigitalHumanId(voice) === human.digital_human_id);
    if (!matchingVoices.length) continue;
    return { human, voice: matchingVoices[matchingVoices.length - 1] };
  }
  return null;
}

function updateSourceVideoHumanFilterControls() {
  const selectedId = value("sourceVideoHumanSelect") || state.digitalHumanId;
  const selected = (state.sourceVideoHumanRows || []).find((human) => human.digital_human_id === selectedId);
  const button = $("hideSourceVideoHumanBtn");
  if (!button) return;
  const isHidden = Boolean(selected && selected.metadata && selected.metadata.hidden_from_source_video);
  button.textContent = isHidden ? "恢复当前形象" : "隐藏当前形象";
}

async function hideCurrentSourceVideoHuman() {
  const digitalHumanId = selectedSourceVideoHumanId();
  const profile = await api(`/digital-humans/${digitalHumanId}`);
  const metadata = profile.metadata || {};
  const hidden = Boolean(metadata.hidden_from_source_video);
  const body = await api(`/digital-humans/${digitalHumanId}`, {
    method: "PATCH",
    body: JSON.stringify({
      metadata: {
        ...metadata,
        hidden_from_source_video: !hidden,
      },
    }),
  });
  if (!hidden) {
    state.digitalHumanId = "";
    state.voiceProfileId = "";
  } else {
    state.digitalHumanId = body.digital_human_id;
  }
  await refreshSourceVideoHumans();
  log(hidden ? "已恢复当前数字人形象。" : "已从制作列表隐藏当前数字人形象。", "ok");
}

async function deleteSourceVideoHuman() {
  const digitalHumanId = selectedSourceVideoHumanId();
  const selected = (state.sourceVideoHumanRows || []).find((human) => human.digital_human_id === digitalHumanId);
  await deleteDigitalHumanById(digitalHumanId, selected ? selected.name || selected.source_video_picker_label : "当前形象");
}

async function cleanupEmptySourceVideoHumans() {
  const rows = (state.sourceVideoHumanRows || []).filter(sourceVideoHumanIsEmptyStub);
  if (!rows.length) {
    log("没有需要清理的空白占位。当前卡片是有素材的历史形象。", "ok");
    return;
  }
  const ok = window.confirm(`确定清理 ${rows.length} 个空白占位吗？\n这些形象没有源视频、头像或云端形象记录。`);
  if (!ok) return;
  let deleted = 0;
  for (const human of rows) {
    try {
      await api(`/digital-humans/${encodeURIComponent(human.digital_human_id)}`, { method: "DELETE" });
      deleted += 1;
      if (state.digitalHumanId === human.digital_human_id) state.digitalHumanId = "";
    } catch (error) {
      log(`清理空形象失败：${human.digital_human_id} / ${error.message || error}`, "error");
    }
  }
  await refreshDigitalHumans();
  await refreshSourceVideoHumans();
  syncCurrentIds();
  log(`已清理 ${deleted} 个空白占位。`, "ok");
}

async function clearAllSourceVideoHumans() {
  const rows = sourceVideoHistoryRows(state.sourceVideoHumanRows || []).visible;
  if (!rows.length) {
    log("当前没有可清空的历史形象。", "ok");
    return;
  }
  const ok = window.confirm(`确定清空 ${rows.length} 个历史形象吗？\n这会删除当前历史形象卡片和对应本地档案。`);
  if (!ok) return;
  const doubleOk = window.confirm("再次确认：清空历史形象后不能在工作台恢复。确定继续吗？");
  if (!doubleOk) return;
  let deleted = 0;
  for (const human of rows) {
    try {
      await api(`/digital-humans/${encodeURIComponent(human.digital_human_id)}`, { method: "DELETE" });
      deleted += 1;
      if (state.digitalHumanId === human.digital_human_id) {
        state.digitalHumanId = "";
        state.voiceProfileId = "";
      }
    } catch (error) {
      log(`删除历史形象失败：${human.digital_human_id} / ${error.message || error}`, "error");
    }
  }
  clearSourceVideoAssetPreview("历史形象已清空");
  clearDownloads();
  await refreshDigitalHumans();
  await refreshSourceVideoHumans();
  syncCurrentIds();
  log(`已清空 ${deleted} 个历史形象。`, "ok");
}

async function deleteDigitalHumanById(digitalHumanId, label = "数字人形象") {
  if (!digitalHumanId) throw new Error("请先选择要删除的形象。");
  const ok = window.confirm(`确定删除「${label}」吗？\n删除后会从工作台移除该数字人形象和本地档案。`);
  if (!ok) return;
  await api(`/digital-humans/${encodeURIComponent(digitalHumanId)}`, {
    method: "DELETE",
  });
  if (state.digitalHumanId === digitalHumanId) {
    state.digitalHumanId = "";
    state.voiceProfileId = "";
    state.roleModelId = "";
    state.taskId = "";
  }
  if ($("humanSelect") && $("humanSelect").value === digitalHumanId) $("humanSelect").value = "";
  if ($("sourceVideoHumanSelect") && $("sourceVideoHumanSelect").value === digitalHumanId) $("sourceVideoHumanSelect").value = "";
  clearSourceVideoAssetPreview("形象已删除，请重新选择");
  clearDownloads();
  await refreshDigitalHumans();
  await refreshSourceVideoHumans();
  syncCurrentIds();
  log(`已删除形象：${label}`, "ok");
}

async function showAllSourceVideoHumans() {
  const checkbox = $("sourceVideoOnlyReadyHumans");
  if (checkbox) checkbox.checked = false;
  await refreshSourceVideoHumans();
}

function selectedSourceVideoHumanId() {
  const selected = value("sourceVideoHumanSelect") || state.digitalHumanId;
  if (!selected) throw new Error("请先创建或选择数字人。");
  state.digitalHumanId = selected;
  return selected;
}

function sourceVideoVoicesForHuman(voices, digitalHumanId) {
  if (!digitalHumanId) return [];
  return (voices || []).filter((voice) => voiceOwnerDigitalHumanId(voice) === digitalHumanId);
}

function sourceVideoDisplayVoices(voices, digitalHumanId) {
  const rows = [...(voices || [])];
  if (!digitalHumanId) return rows;
  return rows.sort((left, right) => {
    const leftOwnsHuman = voiceOwnerDigitalHumanId(left) === digitalHumanId;
    const rightOwnsHuman = voiceOwnerDigitalHumanId(right) === digitalHumanId;
    if (leftOwnsHuman === rightOwnsHuman) return 0;
    return leftOwnsHuman ? -1 : 1;
  });
}

function voiceProfileProviderId(voice) {
  const metadata = (voice && voice.metadata) || {};
  return String((voice && voice.engine) || metadata.provider || metadata.voice_model || "").toLowerCase();
}

function sourceVideoVoiceMatchesCurrentModel(voice, selection = null) {
  if (!voice) return false;
  const voiceSourceType = String(voice.voice_source_type || "").toLowerCase();
  const metadata = voice && voice.metadata && typeof voice.metadata === "object" ? voice.metadata : {};
  if (voiceSourceType === "preset_voice" || metadata.source === "default_preset_voice_asset") {
    return true;
  }
  const voiceModel = String((selection && selection.voice_model) || "").toLowerCase();
  const provider = voiceProfileProviderId(voice);
  if (voiceModel.startsWith("aliyun_bailian")) {
    return provider.startsWith("aliyun_bailian") || provider === "cosyvoice" || provider === "aliyun";
  }
  if (voiceModel === "hifly_voice_clone") {
    return provider === "hifly";
  }
  return true;
}

function sourceVideoShouldRestrictVoiceModel(selection) {
  const voiceModel = String((selection && selection.voice_model) || "").toLowerCase();
  return voiceModel.startsWith("aliyun_bailian") || voiceModel === "hifly_voice_clone";
}

async function refreshSourceVideoVoices() {
  const select = $("sourceVideoVoiceSelect");
  if (!select) return;
  const previousVoiceId = state.voiceProfileId || value("sourceVideoVoiceSelect");
  state.projectId = value("sourceVideoProject") || state.projectId || value("projectId") || "project_demo";
  const voices = await loadProjectVoiceProfiles();
  if (!voices || !voices.length) {
    state.sourceVideoVoiceRows = [];
    state.voiceProfileId = "";
    fillSelect(select, [], "voice_profile_id", "name", "暂无声音，请先创建声音");
    return;
  }
  const selectedHumanId = value("sourceVideoHumanSelect") || state.digitalHumanId;
  const modelVoices = voices;
  if (!modelVoices.length) {
    state.sourceVideoVoiceRows = [];
    state.voiceProfileId = "";
    fillSelect(select, [], "voice_profile_id", "name", "暂无当前声音模型的声音，点击生成语音会创建");
    return;
  }
  const matchingVoices = sourceVideoVoicesForHuman(modelVoices, selectedHumanId);
  const displayVoices = sourceVideoDisplayVoices(modelVoices, selectedHumanId);
  state.sourceVideoVoiceRows = displayVoices;
  fillSelect(select, displayVoices, "voice_profile_id", "source_video_voice_label", "选择声音");
  if (previousVoiceId && displayVoices.some((voice) => voice.voice_profile_id === previousVoiceId)) {
    state.voiceProfileId = previousVoiceId;
    select.value = previousVoiceId;
  } else if (matchingVoices.length) {
    state.voiceProfileId = matchingVoices[matchingVoices.length - 1].voice_profile_id;
    select.value = state.voiceProfileId;
  } else if (displayVoices.length) {
    state.voiceProfileId = displayVoices[0].voice_profile_id;
    select.value = state.voiceProfileId;
  } else {
    state.voiceProfileId = "";
    select.value = "";
  }
}

function setSourceVideoVoiceSelection(voiceProfileId) {
  state.voiceProfileId = voiceProfileId || "";
  if ($("voiceSelect")) $("voiceSelect").value = state.voiceProfileId;
  if ($("sourceVideoVoiceSelect")) $("sourceVideoVoiceSelect").value = state.voiceProfileId;
}

async function ensureSourceVideoScriptVoiceProfile(digitalHumanId) {
  const selection = await currentProductionModelSelection().catch(() => null);
  const selectedId = value("sourceVideoVoiceSelect") || state.voiceProfileId;
  const selectedVoice = selectedVoiceRow(selectedId);
  if (selectedVoice && sourceVideoVoiceMatchesCurrentModel(selectedVoice, selection)) {
    setSourceVideoVoiceSelection(selectedVoice.voice_profile_id);
    return selectedVoice.voice_profile_id;
  }
  if (selection && selection.voice_model && selection.voice_model.startsWith("aliyun_bailian")) {
    const allVoices = state.sourceVideoAllVoiceRows && state.sourceVideoAllVoiceRows.length
      ? state.sourceVideoAllVoiceRows
      : await loadProjectVoiceProfiles();
    const matchingVoice = (allVoices || [])
      .filter((voice) => sourceVideoVoiceMatchesCurrentModel(voice, selection))
      .find((voice) => voiceOwnerDigitalHumanId(voice) === digitalHumanId);
    if (matchingVoice) {
      setSourceVideoVoiceSelection(matchingVoice.voice_profile_id);
      await refreshSourceVideoVoices();
      await loadSourceVideoAssetPreview();
      return matchingVoice.voice_profile_id;
    }
    if (selectedVoice && voiceProfileProviderId(selectedVoice) === "hifly") {
      showAgentCardStatus("av", "当前是飞影音色，正在按阿里云 CosyVoice 创建可读脚本的声音。", "warn");
    } else {
      showAgentCardStatus("av", "正在按当前阿里云 CosyVoice 模型创建可读脚本的声音。", "warn");
    }
    const created = await createSourceVideoVoiceProfile(digitalHumanId);
    return created.voice_profile_id;
  }
  return selectedSourceVideoVoiceId();
}

function clearSourceVideoAssetPreview(message = "暂无形象预览") {
  state.sourceVideoAssetPreview = null;
  const video = $("sourceVideoAvatarVideoPreview");
  const image = $("sourceVideoAvatarImagePreview");
  const empty = $("sourceVideoAvatarEmptyPreview");
  const audio = $("sourceVideoAssetVoicePreview");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.classList.add("is-hidden");
  }
  if (image) {
    image.removeAttribute("src");
    image.classList.add("is-hidden");
  }
  if (empty) {
    empty.textContent = message;
    empty.classList.remove("is-hidden");
  }
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
  }
  write("sourceVideoAssetHumanName", "-");
  write("sourceVideoAssetVoiceName", "-");
}

function setSourceVideoAssetMedia(preview) {
  const video = $("sourceVideoAvatarVideoPreview");
  const image = $("sourceVideoAvatarImagePreview");
  const empty = $("sourceVideoAvatarEmptyPreview");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.classList.add("is-hidden");
  }
  if (image) {
    image.removeAttribute("src");
    image.classList.add("is-hidden");
  }
  if (empty) empty.classList.add("is-hidden");
  if (!preview || !preview.avatar_url) {
    if (empty) {
      empty.textContent = "暂无形象预览";
      empty.classList.remove("is-hidden");
    }
    return;
  }
  if (preview.avatar_media_type === "image" && image) {
    image.src = preview.avatar_url;
    image.classList.remove("is-hidden");
    return;
  }
  if (preview.avatar_media_type === "video" && video) {
    video.src = preview.avatar_url;
    video.classList.remove("is-hidden");
    return;
  }
  if (empty) {
    empty.textContent = "暂不支持此素材预览";
    empty.classList.remove("is-hidden");
  }
}

async function loadSourceVideoAssetPreview() {
  const digitalHumanId = value("sourceVideoHumanSelect") || state.digitalHumanId;
  if (!digitalHumanId) {
    clearSourceVideoAssetPreview("选择数字人后预览形象");
    return null;
  }
  const voiceProfileId = value("sourceVideoVoiceSelect") || state.voiceProfileId;
  const query = voiceProfileId ? `?voice_profile_id=${encodeURIComponent(voiceProfileId)}` : "";
  const preview = await api(`/digital-humans/${digitalHumanId}/asset-preview${query}`);
  state.sourceVideoAssetPreview = preview;
  write("sourceVideoAssetHumanName", preview.name || digitalHumanId);
  const selectedVoice = (preview.voices || []).find((voice) => voice.voice_profile_id === preview.voice_profile_id);
  write("sourceVideoAssetVoiceName", selectedVoice ? selectedVoice.name : preview.voice_profile_id || "-");
  setSourceVideoAssetMedia(preview);
  const audio = $("sourceVideoAssetVoicePreview");
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
    if (preview.voice_sample_url) audio.src = preview.voice_sample_url;
  }
  return preview;
}

async function previewSourceVideoVoice() {
  let preview = state.sourceVideoAssetPreview;
  if (!preview || preview.digital_human_id !== (value("sourceVideoHumanSelect") || state.digitalHumanId)) {
    preview = await loadSourceVideoAssetPreview();
  }
  const audio = $("sourceVideoVoicePreview") || $("sourceVideoAssetVoicePreview");
  const assetAudio = $("sourceVideoAssetVoicePreview");
  const digitalHumanId = selectedSourceVideoHumanId();
  const voiceProfileId = await ensureSourceVideoScriptVoiceProfile(digitalHumanId);
  const text = sourceVideoVoicePreviewText();
  const controls = sourceVideoVoiceControls();
  showAgentCardStatus("av", `正在用当前${sourceVideoLanguageLabel()}脚本合成克隆声音试听。`, "warn");
  const body = await api(`/digital-humans/${digitalHumanId}/voice-profiles/${voiceProfileId}/test`, {
    method: "POST",
    body: JSON.stringify({
      text,
      language: sourceVideoLanguage(),
      voice_style: controls.voice_style,
      speech_rate: controls.speech_rate,
      confirm_paid_call: cloudPaidCallConfirmed(),
      allow_sample_fallback: false,
    }),
  });
  const audioUrl = body.audio_url ? `${body.audio_url}${body.audio_url.includes("?") ? "&" : "?"}preview=${Date.now()}` : "";
  if (audio) {
    audio.src = audioUrl;
    audio.load();
    await audio.play().catch(() => {
      showAgentCardStatus("av", "克隆声音试听已生成，请点击播放器播放。", "ok");
    });
  }
  if (assetAudio && assetAudio !== audio && audioUrl) {
    assetAudio.src = audioUrl;
    assetAudio.load();
  }
  state.sourceVideoAssetPreview = { ...(preview || {}), voice_test_url: body.audio_url };
  showAgentCardStatus("av", "已用当前脚本文案生成克隆声音试听。", "ok");
  log("已用当前脚本文案生成克隆声音试听。", "ok");
}

function selectedSourceVideoVoiceId() {
  const selected = value("sourceVideoVoiceSelect") || state.voiceProfileId;
  if (!selected) throw new Error("请先完成第一步，创建或选择声音。");
  state.voiceProfileId = selected;
  return selected;
}

async function currentProductionModelSelection() {
  if (state.currentModelSelection) return state.currentModelSelection;
  const body = await api("/models/selection");
  state.currentModelSelection = body.selection || null;
  return state.currentModelSelection;
}

async function sourceVideoUsesHifly() {
  const selection = await currentProductionModelSelection();
  if (selection && selection.digital_human_model === "hifly") return true;
  if (!state.desktopSettings) {
    try {
      state.desktopSettings = await api("/settings/desktop");
    } catch (_error) {
      return false;
    }
  }
  return Boolean(state.desktopSettings && state.desktopSettings.CLOUD_VIDEO_PROVIDER === "hifly");
}

async function sourceVideoUsesHiflyVoice() {
  const selection = await currentProductionModelSelection();
  if (selection && selection.voice_model === "hifly_voice_clone") return true;
  if (!state.desktopSettings) {
    try {
      state.desktopSettings = await api("/settings/desktop");
    } catch (_error) {
      return false;
    }
  }
  return Boolean(state.desktopSettings && state.desktopSettings.CLOUD_VOICE_PROVIDER === "hifly_voice_clone");
}

async function uploadSourceVideo(digitalHumanIdOverride = "") {
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const fileInput = $("sourceVideoFile");
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;
  if (!file) throw new Error("请先选择源视频文件。");
  const contentBase64 = await readFileAsBase64(file);
  const body = await api(`/digital-humans/${digitalHumanId}/source-video/upload`, {
    method: "POST",
    body: JSON.stringify({
      filename: file.name || "source_video.mp4",
      content_type: file.type || "video/mp4",
      content_base64: contentBase64,
    }),
  });
  state.sourceVideoUploaded = true;
  setSourceVideoProgress(20, "源视频已上传", "源视频已保存并完成基础检测。", "running");
  writeJson("sourceVideoProgressBox", body);
  await refreshHumanReadiness();
  await loadSourceVideoAssetPreview();
  syncCurrentIds();
  log("源视频已上传并完成检测。", "ok");
}

async function extractSourceVideoVoice(digitalHumanIdOverride = "") {
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const body = await api(`/digital-humans/${digitalHumanId}/source-video/extract-voice`, {
    method: "POST",
    body: "{}",
  });
  setSourceVideoProgress(30, "声音样本已提取", "已从源视频提取声音样本，准备创建声音档案。", "running");
  writeJson("sourceVideoProgressBox", body);
  log("源视频声音样本已提取。", "ok");
}

async function createSourceVideoVoiceProfile(digitalHumanIdOverride = "") {
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const body = await api(`/digital-humans/${digitalHumanId}/source-video/create-voice-profile`, {
    method: "POST",
    body: JSON.stringify({
      name: `${value("sourceVideoHumanName") || value("humanName") || "源视频"}音色`,
      confirm_paid_call: cloudPaidCallConfirmed(),
      provider: "aliyun_bailian_cosyvoice",
      source_audio_url: value("sourceVideoPublicAudioUrl") || null,
      metadata: {},
    }),
  });
  state.voiceProfileId = body.voice_profile_id;
  if ($("voiceSelect")) $("voiceSelect").value = state.voiceProfileId;
  if ($("sourceVideoVoiceSelect")) $("sourceVideoVoiceSelect").value = state.voiceProfileId;
  await refreshVoiceProfiles();
  await refreshSourceVideoVoices();
  await loadSourceVideoAssetPreview();
  setSourceVideoProgress(45, "声音档案已创建", "形象和声音已准备好，可以生成视频。", "running");
  writeJson("sourceVideoProgressBox", body);
  syncCurrentIds();
  log(`源视频声音档案已创建：${state.voiceProfileId}`, "ok");
  return body;
}

async function prepareHiflySourceAvatar(digitalHumanIdOverride = "") {
  if (!(await sourceVideoUsesHifly())) return null;
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const title = value("sourceVideoHumanName") || "源视频数字人";
  const confirmPaid = cloudPaidCallConfirmed();
  const metadata = { source: "simple_three_step" };
  const avatar = await api(`/digital-humans/${digitalHumanId}/source-video/hifly/create-avatar`, {
    method: "POST",
    body: JSON.stringify({ title, confirm_paid_call: confirmPaid, metadata }),
  });
  return avatar;
}

async function prepareHiflySourceAssets(digitalHumanIdOverride = "") {
  if (!(await sourceVideoUsesHifly())) return null;
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const avatar = await prepareHiflySourceAvatar(digitalHumanId);
  const voiceResult = await prepareHiflySourceVoice(digitalHumanId);
  return { avatar, voice: voiceResult.voice };
}

async function prepareHiflySourceVoice(digitalHumanIdOverride = "") {
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const title = value("sourceVideoHumanName") || "源视频数字人";
  const confirmPaid = cloudPaidCallConfirmed();
  const metadata = { source: "simple_three_step", voice_model: "hifly_voice_clone" };
  const voice = await api(`/digital-humans/${digitalHumanId}/source-video/hifly/create-voice`, {
    method: "POST",
    body: JSON.stringify({ title, voice_type: "clone", confirm_paid_call: confirmPaid, metadata }),
  });
  return { voice };
}

async function createHiflySourceVideoVoiceProfile(hifly, digitalHumanIdOverride = "") {
  const digitalHumanId = digitalHumanIdOverride || selectedSourceVideoHumanId();
  const voice = hifly && hifly.voice ? hifly.voice : {};
  const body = await api(`/digital-humans/${digitalHumanId}/voice-profiles`, {
    method: "POST",
    body: JSON.stringify({
      name: `${value("sourceVideoHumanName") || "源视频"}音色`,
      voice_source_type: "source_video_audio",
      engine: "hifly",
      metadata: {
        source: "source_video_audio",
        provider: "hifly",
        provider_voice_id: voice.voice_id || "",
        hifly_avatar: hifly ? hifly.avatar : null,
        hifly_voice: voice,
      },
    }),
  });
  state.voiceProfileId = body.voice_profile_id;
  if ($("sourceVideoVoiceSelect")) $("sourceVideoVoiceSelect").value = state.voiceProfileId;
  await refreshSourceVideoVoices();
  await loadSourceVideoAssetPreview();
  setSourceVideoProgress(45, "飞影音色已登记", "飞影声音已经绑定到当前数字人。", "running");
  syncCurrentIds();
  log(`飞影音色已登记：${state.voiceProfileId}`, "ok");
  return body;
}

async function sourceVideoPrepareProfile() {
  state.projectId = value("sourceVideoProject") || state.projectId || value("projectId") || "project_demo";
  if ($("sourceVideoProject")) $("sourceVideoProject").value = state.projectId;
  if ($("projectId")) $("projectId").value = state.projectId;
  let digitalHumanId = "";
  let createdNewHuman = false;
  let sourceVideoUploadCompleted = false;
  state.sourceVideoProfilePreparing = true;
  try {
    const created = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-humans`, {
      method: "POST",
      body: JSON.stringify({
        name: value("sourceVideoHumanName") || "源视频数字人",
        avatar_source_type: "uploaded_reference",
      }),
    });
    digitalHumanId = created.digital_human_id;
    createdNewHuman = true;
    state.digitalHumanId = digitalHumanId;
    state.sourceVideoLastPreparedHumanId = digitalHumanId;
    await uploadSourceVideo(digitalHumanId);
    sourceVideoUploadCompleted = true;
    const cloneVoice = checked("sourceVideoCloneVoice");
    const useHiflyVideo = await sourceVideoUsesHifly();
    const useHiflyVoice = await sourceVideoUsesHiflyVoice();
    let hifly = null;
    let voice = null;
    if (useHiflyVideo) {
      hifly = { avatar: await prepareHiflySourceAvatar(digitalHumanId), voice: null };
    }
    if (cloneVoice) {
      await extractSourceVideoVoice(digitalHumanId);
      if (useHiflyVoice) {
        try {
          const hiflyVoice = await prepareHiflySourceVoice(digitalHumanId);
          hifly = { ...(hifly || {}), voice: hiflyVoice.voice };
          voice = await createHiflySourceVideoVoiceProfile(hifly, digitalHumanId);
        } catch (error) {
          log("飞影声音克隆失败，已自动回退阿里云声音克隆。", "error");
          console.warn("Hifly voice clone failed; falling back to Aliyun.", error);
          voice = await createSourceVideoVoiceProfile(digitalHumanId);
        }
      } else {
        voice = await createSourceVideoVoiceProfile(digitalHumanId);
      }
    } else {
      await loadSourceVideoAssetPreview();
      syncCurrentIds();
    }
    writeJson("sourceVideoProgressBox", {
      status: "ready",
      digital_human_id: state.digitalHumanId,
      voice_profile_id: cloneVoice ? state.voiceProfileId : value("sourceVideoVoiceSelect") || state.voiceProfileId || null,
      voice_clone_skipped: !cloneVoice,
      hifly,
      voice,
    });
    log(cloneVoice ? "形象和声音已准备好。" : "数字人形象已准备好，未克隆声音。", "ok");
  } catch (error) {
    if (createdNewHuman && digitalHumanId && !sourceVideoUploadCompleted) {
      try {
        await api(`/digital-humans/${encodeURIComponent(digitalHumanId)}`, { method: "DELETE" });
        if (state.digitalHumanId === digitalHumanId) state.digitalHumanId = "";
        state.sourceVideoLastPreparedHumanId = "";
      } catch (_cleanupError) {
        log("视频上传失败，临时空形象清理失败，请在历史形象里手动删除。", "error");
      }
    }
    throw error;
  } finally {
    state.sourceVideoProfilePreparing = false;
    await refreshSourceVideoHumans();
    if ($("sourceVideoHumanSelect") && (state.sourceVideoHumanPickerRows || []).some((human) => human.digital_human_id === digitalHumanId)) {
      $("sourceVideoHumanSelect").value = digitalHumanId;
    }
    syncCurrentIds();
  }
}

function saveSourceVideoScript() {
  const script = syncSourceVideoScriptStateFromInput();
  if (!script) throw new Error("请先填写脚本。");
  setSourceVideoProgress(35, "脚本已保存", "脚本已保存，下一步可以生成数字人视频。", "running");
  writeJson("sourceVideoProgressBox", {
    status: "script_saved",
    script_preview: script.slice(0, 120),
  });
  log("脚本已保存。", "ok");
}

async function createSourceVideoTask() {
  requireProject();
  const digitalHumanId = selectedSourceVideoHumanId();
  const voiceProfileId = await ensureSourceVideoScriptVoiceProfile(digitalHumanId);
  if (!voiceProfileId) throw new Error("请先完成第一步，创建或选择声音。");
  const script = syncSourceVideoScriptStateFromInput();
  if (!script) throw new Error("请先填写新脚本。");
  const quality = value("sourceVideoRenderQuality") || "final";
  const controls = sourceVideoVoiceControls();
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-human-tasks`, {
    method: "POST",
    body: JSON.stringify({
      digital_human_id: digitalHumanId,
      voice_profile_id: voiceProfileId,
      topic: script.slice(0, 60) || "源视频数字人",
      fixed_script: script,
      render_profile: quality === "final" ? "final" : "preview",
      script_review_required: false,
      export_jianying_draft: false,
      metadata: {
        source_video_workflow: true,
        language: sourceVideoLanguage(),
        voice_style: controls.voice_style,
        voice_style_label: controls.voice_style_label,
        speech_rate: controls.speech_rate,
      },
    }),
  });
  state.taskId = body.task_id;
  state.sourceVideoTaskDraftKey = sourceVideoCurrentTaskDraftKey(script, digitalHumanId, voiceProfileId);
  setSourceVideoTaskRunning(body.initial_status === "running");
  clearDownloads();
  syncCurrentIds();
  setSourceVideoProgress(55, "任务已创建", "已提交视频任务，准备进入云端生成。", "running");
  writeJson("sourceVideoProgressBox", body);
  await loadCurrentTaskDetails({ quiet: true });
  log(`源视频数字人任务已创建：${state.taskId}`, "ok");
}

async function renderSourceVideoTask() {
  if (state.sourceVideoRenderInFlight || state.sourceVideoTaskRunning) {
    log("已有数字人生成任务正在运行，请等待当前任务完成后再提交。", "error");
    return;
  }
  setSourceVideoRenderBusy(true);
  setSourceVideoProgress(60, "准备生成", "正在检查任务状态并准备提交云端。", "running");
  try {
    const runningTasks = await refreshSourceVideoRunningTaskStatus();
    if (runningTasks.length) {
      log("已有数字人生成任务正在运行，请等待当前任务完成后再提交。", "error");
      return;
    }
    if (await sourceVideoUsesHifly()) {
      await renderHiflySourceVideo();
      return;
    }
    if (!sourceVideoTaskMatchesCurrentDraft()) await createSourceVideoTask();
    requireTask();
    startSourceVideoProgressTicker("云端生成中", "正在生成数字人视频，请保持窗口打开。", 65, 92);
    const body = await api(`/tasks/${state.taskId}/cloud-source-video-render`, {
      method: "POST",
      body: JSON.stringify({
        render_quality: value("sourceVideoRenderQuality") || "final",
        confirm_paid_call: sourceVideoCloudGenerationConfirmed(),
        metadata: {},
      }),
    });
    setSourceVideoTaskRunning(body.status === "running");
    writeJson("sourceVideoProgressBox", body);
    await loadCurrentTaskDetails({ quiet: true });
    if (body.status === "completed") {
      finishSourceVideoProgress(true, "源视频数字人成片已生成。");
      enableSourceVideoDownloads();
      log("源视频数字人成片已生成。", "ok");
    } else if (body.status === "failed") {
      finishSourceVideoProgress(false, body.error || "源视频数字人任务失败。");
      log(body.error || "源视频数字人任务失败。", "error");
    } else {
      setSourceVideoProgress(92, "云端生成中", "任务已提交，正在等待云端完成。", "running");
    }
    syncCurrentIds();
  } catch (error) {
    const friendly = sourceVideoRenderFriendlyError(error);
    if (!friendly) throw error;
    if (!friendly.includes("已有数字人生成任务正在运行")) {
      setSourceVideoTaskRunning(false);
    }
    finishSourceVideoProgress(false, friendly);
    writeJson("sourceVideoProgressBox", { status: "blocked", message: friendly });
    log(friendly, "error");
  } finally {
    setSourceVideoRenderBusy(false);
  }
}

async function renderHiflySourceVideo() {
  const digitalHumanId = selectedSourceVideoHumanId();
  const voiceProfileId = await ensureSourceVideoScriptVoiceProfile(digitalHumanId);
  if (!voiceProfileId) throw new Error("请先选择或创建可用声音。");
  const script = syncSourceVideoScriptStateFromInput();
  if (!script) throw new Error("请先填写新脚本。");
  const controls = sourceVideoVoiceControls();
  startSourceVideoProgressTicker("飞影生成中", "飞影正在生成数字人口播视频，请保持窗口打开。", 65, 92);
  const body = await api(`/digital-humans/${digitalHumanId}/source-video/hifly/generate`, {
    method: "POST",
    body: JSON.stringify({
      title: value("sourceVideoHumanName") || "源视频数字人",
      text: script,
      voice_profile_id: voiceProfileId,
      voice_type: "clone",
      confirm_paid_call: sourceVideoCloudGenerationConfirmed(),
      metadata: {
        provider: "hifly",
        source: "simple_three_step",
        language: sourceVideoLanguage(),
        voice_style: controls.voice_style,
        voice_style_label: controls.voice_style_label,
        speech_rate: controls.speech_rate,
      },
    }),
  });
  state.taskId = body.task_id;
  setSourceVideoTaskRunning(body.status === "running");
  writeJson("sourceVideoProgressBox", body);
  if (body.status === "completed") {
    finishSourceVideoProgress(true, "飞影数字人成片已生成。");
    enableSourceVideoDownloads();
    log("飞影数字人成片已生成。", "ok");
  } else if (body.status === "failed") {
    finishSourceVideoProgress(false, body.error || "飞影数字人生成失败。");
    log(body.error || "飞影数字人生成失败。", "error");
  } else {
    setSourceVideoProgress(92, "飞影生成中", "任务已提交，正在等待飞影生成完成。", "running");
  }
  syncCurrentIds();
}

async function loadSourceVideoReport() {
  requireTask();
  const body = await api(`/tasks/${state.taskId}/source-video-report`);
  writeJson("sourceVideoProgressBox", body);
  finishSourceVideoProgress(true, "报告已加载，成片可以预览或下载。");
  enableSourceVideoDownloads();
}

function enableSourceVideoDownloads() {
  requireTask();
  state.sourceVideoCoverTaskId = state.taskId;
  state.sourceVideoCoverVideoPath = "";
  state.sourceVideoCoverPath = "";
  setDownload("downloadSourceVideoVoice", `/tasks/${state.taskId}/download/voice`);
  setDownload("downloadSourceVideoFinal", `/tasks/${state.taskId}/download/final-video`);
  setDownload("downloadSourceVideoArtifacts", `/tasks/${state.taskId}/artifacts.zip`);
  if ($("sourceVideoVoicePreview")) $("sourceVideoVoicePreview").src = `/tasks/${state.taskId}/download/voice`;
  if ($("sourceVideoFinalPreview")) $("sourceVideoFinalPreview").src = `/tasks/${state.taskId}/download/final-video`;
  enableDownloads();
}

async function refreshHumanReadiness() {
  if (!state.digitalHumanId) {
    writeJson("humanReadinessBox", {
      status: "未选择数字人",
      message: "当前只是在管理声音资产，选择或创建数字人后再检查数字人可用性。",
    });
    return null;
  }
  const body = await api(`/digital-humans/${state.digitalHumanId}/readiness`);
  writeJson("humanReadinessBox", body);
  return body;
}

async function generateAvatar() {
  requireHuman();
  const body = await api(`/digital-humans/${state.digitalHumanId}/avatar/generate`, {
    method: "POST",
    body: JSON.stringify({
      prompt: value("avatarPrompt") || "合成数字人主播",
      style: "studio",
      count: 3,
    }),
  });
  const images = body.images || [];
  renderAvatarGallery(images);
  await refreshHumanReadiness();
  log(`已生成 ${images.length} 张头像候选`, "ok");
}

function renderAvatarGallery(images) {
  const gallery = $("avatarGallery");
  if (!gallery) return;
  gallery.className = images.length ? "gallery" : "gallery empty";
  gallery.innerHTML = "";
  if (!images.length) {
    gallery.textContent = "暂无头像候选";
    return;
  }
  for (const image of images) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "avatar-card";
    const avatar = document.createElement("img");
    avatar.alt = "头像候选";
    avatar.src = image.url;
    const label = document.createElement("span");
    label.textContent = image.asset_id;
    card.appendChild(avatar);
    card.appendChild(label);
    card.onclick = () => {
      state.selectedAvatarAssetId = image.asset_id;
      for (const item of gallery.querySelectorAll(".avatar-card")) item.classList.remove("selected");
      card.classList.add("selected");
      log(`已选择头像候选：${image.asset_id}`);
    };
    gallery.appendChild(card);
  }
}

async function selectAvatar() {
  requireHuman();
  if (!state.selectedAvatarAssetId) throw new Error("请先点击一张头像候选。");
  await api(`/digital-humans/${state.digitalHumanId}/avatar/select`, {
    method: "POST",
    body: JSON.stringify({ asset_id: state.selectedAvatarAssetId }),
  });
  await refreshHumanReadiness();
  log(`头像已选定：${state.selectedAvatarAssetId}`, "ok");
}

async function refreshRoleModels() {
  requireHuman();
  const body = await api(`/digital-humans/${state.digitalHumanId}/role-models`);
  const rows = body || [];
  fillSelect($("roleModelSelect"), rows, "role_model_id", "engine_type", "选择已有角色模型");
  renderRows("roleModelList", rows, "role_model_id", "engine_type", "暂无角色模型", (roleModel) => {
    $("roleModelSelect").value = roleModel.role_model_id;
    safeRun(selectRoleModel);
  });
  if (state.roleModelId && $("roleModelSelect")) $("roleModelSelect").value = state.roleModelId;
  syncCurrentIds();
}

async function createRoleModel() {
  requireHuman();
  const body = await api(`/digital-humans/${state.digitalHumanId}/role-models`, {
    method: "POST",
    body: JSON.stringify({
      source_video_asset_id: value("roleSourceVideoPath") || null,
      idle_video_asset_id: value("roleIdleVideoPath") || null,
      action_video_asset_id: value("roleActionVideoPath") || null,
      pkl_model_path: value("rolePklPath") || null,
      engine_type: value("roleEngineType") || "yywav2lip",
    }),
  });
  state.roleModelId = body.role_model_id;
  state.taskId = "";
  clearDownloads();
  await refreshRoleModels();
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`角色模型已创建：${state.roleModelId}`, "ok");
}

async function selectRoleModel() {
  const selected = value("roleModelSelect");
  if (!selected) throw new Error("请先选择角色模型。");
  state.roleModelId = selected;
  state.taskId = "";
  clearDownloads();
  syncCurrentIds();
  log(`已选择角色模型：${selected}`, "ok");
}

async function validateRoleModel() {
  requireHuman();
  if (!state.roleModelId) await selectRoleModel();
  const body = await api(`/digital-humans/${state.digitalHumanId}/role-models/${state.roleModelId}/validate`, {
    method: "POST",
    body: "{}",
  });
  await refreshRoleModels();
  await refreshHumanReadiness();
  log(`角色模型校验：${body.status}`, body.status === "ready" ? "ok" : "error");
}

async function refreshReferences() {
  requireProject();
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/references`);
  const rows = body || [];
  fillSelect($("referenceSelect"), rows, "reference_id", "title", "选择已有参考视频");
  renderRows("referenceList", rows, "reference_id", "title", "暂无参考视频", (reference) => {
    $("referenceSelect").value = reference.reference_id;
    safeRun(selectReference);
  });
  if (state.referenceId && $("referenceSelect")) $("referenceSelect").value = state.referenceId;
  syncCurrentIds();
}

async function createReference() {
  requireProject();
  const payload = {
    title: value("referenceTitle") || "参考视频",
    metadata: { source: "studio" },
  };
  if (value("referenceSourcePath")) payload.source_path = value("referenceSourcePath");
  if (value("referenceAssetId")) payload.asset_id = value("referenceAssetId");
  if (!payload.source_path && !payload.asset_id) {
    throw new Error("请填写本地视频路径或项目素材 ID。");
  }
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/references`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.referenceId = body.reference_id;
  await refreshReferences();
  syncCurrentIds();
  log(`参考视频已创建：${state.referenceId}`, "ok");
}

async function selectReference() {
  const selected = value("referenceSelect");
  if (!selected) throw new Error("请先选择参考视频。");
  state.referenceId = selected;
  syncCurrentIds();
  log(`已选择参考视频：${selected}`, "ok");
}

async function analyzeReference() {
  if (!state.referenceId) await selectReference();
  const body = await api(`/references/${state.referenceId}/analyze`, {
    method: "POST",
    body: "{}",
  });
  log(`参考视频分析完成：${body.status}`, body.status === "analyzed" ? "ok" : "error");
  await loadReferenceAnalysis();
}

async function loadReferenceAnalysis() {
  if (!state.referenceId) await selectReference();
  const body = await api(`/references/${state.referenceId}/analysis`);
  writeJson("referenceAnalysisBox", body);
  log("参考视频分析结果已刷新。", "ok");
}

function rewriteProductInfo() {
  const raw = value("rewriteProductInfo");
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch (_error) {
    return { text: raw };
  }
}

function copywritingStyleLabel() {
  const styles = {
    original: "原风格",
    sales_live: "带货直播口语",
    seeding: "种草文案",
    formal: "正式介绍",
    humor: "幽默风趣",
  };
  return styles[value("rewriteStyle") || "original"] || "原风格";
}

function syncRewriteStyleTone() {
  if ($("rewriteTone")) $("rewriteTone").value = copywritingStyleLabel();
}

function updateRewriteInputCount() {
  const text = value("rewriteProductInfo");
  write("rewriteInputCount", `${text.length}/3500`);
}

function copywritingBody(input, styleLabel, index, mode) {
  const cleanInput = input.replace(/\s+/g, " ").trim();
  const prefix = mode === "rewrite" ? "换个说法，" : "";
  if (styleLabel === "带货直播口语") {
    return `${prefix}姐妹们看这里，${cleanInput}。真正打动人的不是复杂参数，而是它能马上解决你的具体问题。今天这条视频就把重点讲清楚，适合正在犹豫、想少踩坑的人。`;
  }
  if (styleLabel === "种草文案") {
    return `${prefix}我最近发现一个很适合日常使用的选择：${cleanInput}。它的优势不是夸张，而是细节稳定、上手轻松，适合想提升效率又不想折腾的人。`;
  }
  if (styleLabel === "正式介绍") {
    return `${prefix}${cleanInput}。这套方案面向有明确内容生产需求的团队，重点解决效率、稳定性和复用问题，帮助用户更快完成高质量口播内容。`;
  }
  if (styleLabel === "幽默风趣") {
    return `${prefix}${cleanInput}。以前做这件事像在原地转圈，现在终于可以少点纠结，多点产出，把时间花在真正重要的内容上。`;
  }
  const ending = index % 2 === 0 ? "如果你也在做短视频口播，这个方向值得认真试试。" : "先把核心卖点讲明白，再让用户看到真实价值。";
  return `${prefix}${cleanInput}。这条内容适合做数字人口播开场，先抓住痛点，再讲清楚价值，最后给出明确行动理由。${ending}`;
}

function generateLocalCopyScripts(mode = "generate") {
  const input = value("rewriteProductInfo");
  if (!input) throw new Error("请先输入产品信息或粘贴原文案。");
  const count = Math.max(1, Math.min(20, Number(value("rewrittenScriptCount") || 3)));
  const styleLabel = copywritingStyleLabel();
  const scripts = [];
  for (let index = 0; index < count; index += 1) {
    const body = copywritingBody(input, styleLabel, index, mode);
    scripts.push({
      script_id: `${mode}_copy_${index + 1}`,
      title: mode === "rewrite" ? `改写文案 ${index + 1}` : `生成文案 ${index + 1}`,
      hook: body.slice(0, 42),
      body,
      cta: "想继续提升口播转化，可以先用这版脚本测试效果。",
      style: styleLabel,
      source: "local_copywriting",
    });
  }
  return scripts;
}

function showCopyScripts(scripts, mode) {
  state.rewriteId = `local_${mode}_${Date.now()}`;
  renderRewrittenScripts(scripts);
  renderCopywritingResults(scripts);
  log(`已${mode === "rewrite" ? "改写" : "生成"} ${scripts.length} 条文案`, "ok");
}

async function generateCopyScripts() {
  const scripts = generateLocalCopyScripts("generate");
  showCopyScripts(scripts, "generate");
}

function clearCopyInput() {
  if ($("rewriteProductInfo")) $("rewriteProductInfo").value = "";
  renderRewrittenScripts([]);
  renderCopywritingResults([], "等待生成文案。");
  updateRewriteInputCount();
}

async function pasteCopyInput() {
  if (!navigator.clipboard || !navigator.clipboard.readText) {
    throw new Error("当前环境不支持自动读取剪贴板，请使用 Ctrl+V 粘贴。");
  }
  const text = await navigator.clipboard.readText();
  if (!text) throw new Error("剪贴板里没有可粘贴的文字。");
  $("rewriteProductInfo").value = text.slice(0, 3500);
  updateRewriteInputCount();
}

async function generateScripts() {
  requireProject();
  const count = Number(value("rewrittenScriptCount") || 3);
  if (!state.referenceId) {
    const scripts = generateLocalCopyScripts("rewrite");
    showCopyScripts(scripts, "rewrite");
    return;
  }
  const body = await api(`/references/${state.referenceId}/rewrite`, {
    method: "POST",
    body: JSON.stringify({
      reference_id: state.referenceId,
      project_id: state.projectId,
      product_info: rewriteProductInfo(),
      count,
      platform: "douyin",
      tone: value("rewriteTone") || "实用、可信、适合口播",
    }),
  });
  state.rewriteId = body.rewrite_id;
  renderRewrittenScripts(body.scripts || []);
  renderCopywritingResults(body.scripts || []);
  log(`已生成 ${body.scripts.length} 条改写脚本`, "ok");
}

async function refreshRewrites() {
  if (!state.referenceId) await selectReference();
  const body = await api(`/references/${state.referenceId}/rewrites`);
  const latest = (body.rewrites || [])[0];
  if (latest) {
    state.rewriteId = latest.rewrite_id;
    renderRewrittenScripts(latest.scripts || []);
    renderCopywritingResults(latest.scripts || []);
  } else {
    renderRewrittenScripts([]);
    renderCopywritingResults([], "暂无文案结果。");
  }
}

function renderCopywritingResults(scripts, emptyText = "生成后，文案会显示在这里。") {
  const box = $("rewrittenScriptsBox");
  if (!box) return;
  box.innerHTML = "";
  const rows = scripts || [];
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "copy-result-empty";
    empty.textContent = emptyText;
    box.appendChild(empty);
    return;
  }
  for (const script of rows) {
    const card = document.createElement("article");
    card.className = "copy-result-card";

    const header = document.createElement("header");
    const title = document.createElement("h4");
    title.textContent = script.title || "文案";
    const style = document.createElement("span");
    style.className = "copy-result-style";
    style.textContent = script.style || copywritingStyleLabel();
    header.append(title, style);

    const body = document.createElement("p");
    body.className = "copy-result-body";
    body.textContent = script.body || script.hook || "";

    const cta = document.createElement("p");
    cta.className = "copy-result-cta";
    cta.textContent = script.cta || "可直接选为视频脚本。";

    card.append(header, body, cta);
    box.appendChild(card);
  }
}

function renderRewrittenScripts(scripts) {
  state.rewrittenScripts = scripts || [];
  const select = $("rewrittenScriptSelect");
  if (!select) return;
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "选择脚本";
  select.appendChild(empty);
  for (const script of scripts) {
    const option = document.createElement("option");
    option.value = script.script_id;
    option.textContent = script.title || "文案";
    option.dataset.script = JSON.stringify(script);
    select.appendChild(option);
  }
  if (state.rewrittenScripts.length) select.value = state.rewrittenScripts[0].script_id;
}

async function selectScriptForTask() {
  const select = $("rewrittenScriptSelect");
  const option = select.options[select.selectedIndex];
  if (!option || !option.value) throw new Error("请先选择一条改写脚本。");
  state.selectedRewriteScript = JSON.parse(option.dataset.script);
  if ($("topic")) $("topic").value = state.selectedRewriteScript.title || state.selectedRewriteScript.hook || $("topic").value;
  const scriptText = state.selectedRewriteScript.body || state.selectedRewriteScript.script || state.selectedRewriteScript.hook || "";
  if (scriptText) setSourceVideoScriptText(scriptText, "已把所选脚本填入工作台。");
  if ($("reviewRequired")) $("reviewRequired").checked = true;
  switchView("source-video-human");
  log(`已选择脚本用于视频任务：${state.selectedRewriteScript.script_id}`, "ok");
}

function campaignTopics() {
  return value("campaignTopics")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function selectedCampaignTemplate() {
  const selected = value("campaignTemplateSelect") || state.videoTemplateId || "clean_talking_head";
  state.videoTemplateId = selected;
  return selected;
}

async function createCampaign() {
  requireProject();
  requireHuman();
  requireVoice();
  const source = value("campaignSource") || "topics";
  const payload = {
    name: value("campaignName") || "短视频批量生产",
    digital_human_id: state.digitalHumanId,
    voice_profile_id: state.voiceProfileId,
    role_model_id: state.roleModelId || null,
    render_profile: "batch",
    video_template_id: selectedCampaignTemplate(),
    export_jianying_draft: true,
    script_review_required: false,
    topics: [],
    rewritten_scripts: [],
    csv_text: null,
    metadata: { source },
  };
  if (source === "rewrites") {
    payload.rewritten_scripts = state.rewrittenScripts.length
      ? state.rewrittenScripts
      : state.selectedRewriteScript
        ? [state.selectedRewriteScript]
        : [];
    if (!payload.rewritten_scripts.length) throw new Error("请先生成改写脚本。");
  } else if (source === "csv") {
    payload.csv_text = value("campaignCsvText");
    if (!payload.csv_text) throw new Error("请选择 CSV 文件或粘贴 CSV 文本。");
  } else {
    payload.topics = campaignTopics();
    if (!payload.topics.length) throw new Error("请至少粘贴一个批量选题。");
  }
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/campaigns`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.campaignId = body.campaign_id;
  writeJson("campaignBox", body);
  setDownload("downloadCampaign", `/campaigns/${state.campaignId}/download.zip`);
  log(`批量任务已创建：${state.campaignId}`, "ok");
}

async function runCampaign(retryFailed = false) {
  if (!state.campaignId) await createCampaign();
  const body = await api(`/campaigns/${state.campaignId}/run`, {
    method: "POST",
    body: JSON.stringify({ retry_failed: retryFailed }),
  });
  writeJson("campaignBox", body);
  setDownload("downloadCampaign", `/campaigns/${state.campaignId}/download.zip`);
  log(`批量任务状态：${body.status}`, body.status === "completed" ? "ok" : "");
  await loadCampaignProgress();
}

async function loadCampaignProgress() {
  if (!state.campaignId) throw new Error("请先创建批量任务。");
  const body = await api(`/campaigns/${state.campaignId}/tasks`);
  writeJson("campaignBox", body);
  setDownload("downloadCampaign", `/campaigns/${state.campaignId}/download.zip`);
}

async function loadCampaignCsvFile() {
  const input = $("campaignCsvFile");
  const file = input && input.files ? input.files[0] : null;
  if (!file) return;
  $("campaignCsvText").value = await file.text();
  log(`CSV 已读取：${file.name}`, "ok");
}

async function refreshVoiceProfiles() {
  requireProject();
  const voices = await loadProjectVoiceProfiles();
  state.voiceProfileRows = voices;
  fillSelect($("voiceSelect"), voices, "voice_profile_id", "source_video_voice_label", "选择已有声音");
  renderRows("voiceList", voices, "voice_profile_id", "source_video_voice_label", "暂无历史声音", (voice) => {
    $("voiceSelect").value = voice.voice_profile_id;
    safeRun(selectVoiceProfile);
  });
  if (state.voiceProfileId && $("voiceSelect")) $("voiceSelect").value = state.voiceProfileId;
  syncCurrentIds();
}

async function createVoiceProfile() {
  requireHuman();
  const sampleInput = $("voiceSampleFile");
  const sampleFile = sampleInput && sampleInput.files ? sampleInput.files[0] : null;
  if (!sampleFile) throw new Error("请先上传一段声音样本。");
  const sampleUpload = await fileUploadPayload(sampleFile);
  const body = await api(`/digital-humans/${state.digitalHumanId}/voice-profiles`, {
    method: "POST",
    body: JSON.stringify({
      name: value("voiceName") || "合成口播声音",
      voice_source_type: "uploaded_sample",
      engine: "local_sample",
      sample_audio_filename: sampleUpload.filename,
      sample_audio_content_type: sampleUpload.content_type,
      sample_audio_base64: sampleUpload.content_base64,
      metadata: {
        language: value("voiceLanguage") || "zh",
        reference_text: value("voiceText") || "",
      },
    }),
  });
  state.voiceProfileId = body.voice_profile_id;
  state.taskId = "";
  clearDownloads();
  await refreshVoiceProfiles();
  if ($("voiceSelect")) $("voiceSelect").value = state.voiceProfileId;
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`声音已创建：${state.voiceProfileId}`, "ok");
}

async function selectVoiceProfile() {
  const selected = value("voiceSelect");
  if (!selected) throw new Error("请先选择声音。");
  state.voiceProfileId = selected;
  state.taskId = "";
  clearDownloads();
  await refreshHumanReadiness();
  syncCurrentIds();
  log(`已选择声音：${selected}`, "ok");
}

async function deleteVoiceProfile(voice = null) {
  requireProject();
  const voiceProfileId = (voice && voice.voice_profile_id) || value("voiceSelect") || state.voiceProfileId;
  if (!voiceProfileId) throw new Error("请先选择要删除的声音。");
  const ownerDigitalHumanId = selectedVoiceOwnerDigitalHumanId(voice);
  if (!ownerDigitalHumanId) throw new Error("找不到这个声音所属的数字人，请先刷新声音列表。");
  const label = (voice && voice.name) || "当前声音";
  const ok = window.confirm(`确定删除「${label}」吗？\n删除后会从工作台移除该声音档案，本地试听缓存也会清理。`);
  if (!ok) return;
  await api(`/digital-humans/${encodeURIComponent(ownerDigitalHumanId)}/voice-profiles/${encodeURIComponent(voiceProfileId)}`, {
    method: "DELETE",
  });
  if (state.voiceProfileId === voiceProfileId) state.voiceProfileId = "";
  if ($("voiceSelect") && $("voiceSelect").value === voiceProfileId) $("voiceSelect").value = "";
  const audio = $("voicePreview");
  if (audio) {
    audio.pause();
    if (state.voicePreviewObjectUrl) {
      URL.revokeObjectURL(state.voicePreviewObjectUrl);
      state.voicePreviewObjectUrl = "";
    }
    audio.removeAttribute("src");
    audio.load();
  }
  await refreshVoiceProfiles();
  await refreshHumanReadiness();
  if ($("sourceVideoVoiceSelect")) {
    await refreshSourceVideoVoices();
    await loadSourceVideoAssetPreview();
  }
  syncCurrentIds();
  log(`已删除声音：${label}`, "ok");
}

async function playVoiceSample() {
  requireVoice();
  const ownerDigitalHumanId = selectedVoiceOwnerDigitalHumanId();
  if (!ownerDigitalHumanId) throw new Error("找不到这个声音所属的数字人，请先刷新声音列表。");
  const button = $("playVoiceSampleBtn");
  if (button) button.disabled = true;
  try {
    const url = `/digital-humans/${encodeURIComponent(ownerDigitalHumanId)}/voice-profiles/${encodeURIComponent(state.voiceProfileId)}/sample-audio?v=${Date.now()}`;
    const response = await fetch(url);
    if (!response.ok) {
      const detail = await responseErrorDetail(response);
      throw new Error(detail || "没有找到本地原始样本。");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    await playVoicePreviewSource(objectUrl, "正在播放本地原始样本，不会消耗云端额度。", { objectUrl: true });
  } finally {
    if (button) button.disabled = false;
  }
}

async function testVoice() {
  requireVoice();
  const ownerDigitalHumanId = selectedVoiceOwnerDigitalHumanId();
  if (!ownerDigitalHumanId) throw new Error("找不到这个声音所属的数字人，请先刷新声音列表。");
  const button = $("testVoiceBtn");
  if (button) button.disabled = true;
  try {
    const body = await api(`/digital-humans/${ownerDigitalHumanId}/voice-profiles/${state.voiceProfileId}/test`, {
      method: "POST",
      body: JSON.stringify({
        text: value("voiceText") || "声音测试",
        confirm_paid_call: cloudPaidCallConfirmed(),
        allow_sample_fallback: false,
      }),
    });
    const message = body.cached ? "正在播放本地克隆试听缓存，没有重复调用云端。" : "克隆试听已生成并缓存到本地。";
    await playVoicePreviewSource(body.audio_url, message);
  } finally {
    if (button) button.disabled = false;
  }
}

async function createVideoRemixTask() {
  requireProject();
  const generateButton = $("videoRemixGenerateBtn");
  const selectedPath = value("remixMainVideoSelect");
  const selectedVideo = state.remixMainVideos.find((video) => video.path === selectedPath) || null;
  const mainFileInput = $("remixMainVideoFile");
  const mainFile = mainFileInput && mainFileInput.files ? mainFileInput.files[0] : null;
  const assetInput = $("remixAssetFiles");
  const assetFiles = assetInput && assetInput.files ? Array.from(assetInput.files) : [];

  if (!selectedPath && !mainFile) throw new Error("请先选择或上传成片视频。");
  if (!assetFiles.length) throw new Error("请先上传至少一个产品图或素材视频。");

  if (generateButton) {
    generateButton.disabled = true;
    generateButton.textContent = "生成中...";
  }
  clearVideoRemixResult("正在生成混剪结果，请稍等。");
  writeJson("videoRemixStatusBox", {
    "状态": "生成中",
    "提示": "正在本地混剪，多张素材会按顺序插入，请不要重复点击。",
    "素材数量": assetFiles.length,
    "生成数量": state.remixOutputCount || 1,
  });
  try {
    const payload = {
      project_id: state.projectId || value("projectId") || "project_demo",
      main_video_path: mainFile ? "" : selectedPath,
      main_video: mainFile ? await fileUploadPayload(mainFile) : null,
      assets: [],
      output_count: state.remixOutputCount || 1,
      add_subtitles: Boolean($("remixAddSubtitles") && $("remixAddSubtitles").checked),
      subtitle_text: value("remixSubtitleText") || (selectedVideo && selectedVideo.script_text) || null,
      ...sourceVideoBgmPayload(),
    };
    for (const file of assetFiles) {
      payload.assets.push(await fileUploadPayload(file));
    }
    const body = await api("/video-remix/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    writeJson("videoRemixStatusBox", body);
    renderVideoRemixResult(body);
    log(body.message || `本地混剪已完成：${body.remix_task_id}`, "ok");
  } finally {
    if (generateButton) {
      generateButton.disabled = false;
      generateButton.textContent = "一键生成混剪视频";
    }
  }
}

async function createVideoTask() {
  requireProject();
  requireHuman();
  requireVoice();
  const renderProfile = $("renderProfile").value;
  previewVideoTemplate();
  if (renderProfile === "compat" && !state.roleModelId) {
    throw new Error("兼容模式需要先创建、选择并校验角色模型。");
  }
  const payload = {
    digital_human_id: state.digitalHumanId,
    voice_profile_id: state.voiceProfileId,
    topic: value("topic") || "AI IP 口播主题",
    platform: "douyin",
    duration_seconds: 45,
    render_profile: renderProfile,
    video_template_id: state.videoTemplateId || "clean_talking_head",
    script_review_required: $("reviewRequired").checked,
    export_jianying_draft: true,
    metadata: {},
  };
  if (state.selectedRewriteScript) {
    payload.metadata.selected_rewrite_script = state.selectedRewriteScript;
    payload.metadata.fixed_script = [
      state.selectedRewriteScript.hook,
      state.selectedRewriteScript.body,
      state.selectedRewriteScript.cta,
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (state.roleModelId) payload.role_model_id = state.roleModelId;
  const body = await api(`/projects/${encodeURIComponent(state.projectId)}/digital-human-tasks`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.taskId = body.task_id;
  clearDownloads();
  syncCurrentIds();
  log(`视频任务已创建：${state.taskId}`, "ok");
  await trackProgress();
}

async function generateScript() {
  if (!state.taskId) await createVideoTask();
  requireTask();
  log("开始生成脚本...");
  const body = await api(`/tasks/${state.taskId}/run`, { method: "POST", body: "{}" });
  write("taskStatus", body.status);
  await loadScript();
  if (body.status === "waiting_for_review") {
    log("脚本已生成，等待审核。", "ok");
    switchView("task-detail");
  } else if (body.status === "completed") {
    enableDownloads();
    log("脚本和视频已完成。", "ok");
    switchView("results");
  }
  await trackProgress();
}

async function renderVideo() {
  requireTask();
  log("开始渲染视频...");
  const body = await api(`/tasks/${state.taskId}/run`, { method: "POST", body: "{}" });
  write("taskStatus", body.status);
  if (body.status === "waiting_for_review") {
    await loadScript();
    log("脚本等待审核，请查看脚本后点击“审核脚本”。", "ok");
    switchView("task-detail");
  } else if (body.status === "completed") {
    enableDownloads();
    log("视频渲染完成。", "ok");
    switchView("results");
  } else if (body.status === "failed") {
    log(body.error || "任务失败。", "error");
  }
  await trackProgress();
}

async function loadScript() {
  requireTask();
  const body = await api(`/tasks/${state.taskId}/script`);
  write("scriptBox", JSON.stringify(body.script_json, null, 2) + "\n\n" + body.subtitles);
}

async function reviewScript() {
  requireTask();
  await api(`/tasks/${state.taskId}/review/approve`, {
    method: "POST",
    body: JSON.stringify({ reviewer_id: "studio", review_note: "已在工作台审核通过" }),
  });
  log("脚本已审核通过，继续渲染...");
  await renderVideo();
}

async function trackProgress() {
  requireTask();
  const body = await api(`/tasks/${state.taskId}/progress`);
  write("taskStatus", body.status);
  const steps = (body.steps || []).map((step) => `${step.name}: ${step.status}`).join("\n");
  if (steps) log(`当前进度\n${steps}`);
  if (body.status === "completed") enableDownloads();
  syncCurrentIds();
}

function enableDownloads() {
  requireTask();
  setDownload("downloadFinal", `/tasks/${state.taskId}/download/final-video`);
  setDownload("downloadJianying", `/tasks/${state.taskId}/download/jianying-draft`);
  setDownload("downloadPublish", `/tasks/${state.taskId}/download/publish-package`);
  setDownload("downloadQuality", `/tasks/${state.taskId}/download/quality-reports`);
  setDownload("downloadAll", `/tasks/${state.taskId}/artifacts.zip`);
}

async function previewResults() {
  requireTask();
  enableDownloads();
  $("videoPreview").src = `/tasks/${state.taskId}/download/final-video`;
  await trackProgress();
  switchView("results");
  log("成片预览已刷新。", "ok");
}

async function createPublishQueueItem() {
  requireTask();
  const platform = selectedPublishPlatform();
  const body = await api(`/tasks/${state.taskId}/publish/queue`, {
    method: "POST",
    body: JSON.stringify({
      platform,
      scheduled_at: value("publishScheduledAt") || null,
      reviewer_note: value("publishReviewerNote") || null,
      title: value("sourceVideoGeneratedTitle") || null,
      description: value("sourceVideoScript") || null,
      hashtags: sourceVideoPublishHashtags(),
      cover_text: sourceVideoCoverKeyword() || null,
      metadata: {
        cover_image_path: state.sourceVideoCoverPath || null,
      },
    }),
  });
  state.publishQueueId = body.queue_id;
  $("publishStatus").value = body.status;
  setDownload("downloadPublishHandoff", `/publish/queue/${state.publishQueueId}/handoff.zip`);
  writeJson("publishStatusBoard", body);
  renderPublishAutomationStatus(body.metadata && body.metadata.browser_publish ? body.metadata.browser_publish : null);
  await refreshPublishConsole();
  log(`发布包已创建：${state.publishQueueId}`, "ok");
}

async function updatePublishStatus() {
  if (!state.publishQueueId) throw new Error("请先创建发布包。");
  const body = await api(`/publish/queue/${state.publishQueueId}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: value("publishStatus") || null,
      scheduled_at: value("publishScheduledAt") || null,
      reviewer_note: value("publishReviewerNote") || null,
      external_url: value("publishExternalUrl") || null,
    }),
  });
  writeJson("publishStatusBoard", body);
  await refreshPublishConsole();
  log(`发布状态已更新：${body.status}`, "ok");
}

async function refreshPublishConsole() {
  try {
    const board = await api("/publish/board");
    writeJson("publishStatusBoard", board);
  } catch (error) {
    write("publishStatusBoard", error.message || String(error));
  }
  await loadPublishCalendar();
  await loadPublishAutomationStatus();
}

async function loadPublishCalendar() {
  const calendar = await api("/publish/calendar");
  writeJson("publishCalendar", calendar);
}

function publishPlatformLabel(platform) {
  return {
    douyin: "抖音",
    xiaohongshu: "小红书",
    kuaishou: "快手",
    shipinhao: "视频号",
    tiktok: "TikTok",
  }[platform] || platform || "抖音";
}

function selectedPublishPlatform() {
  const checked = document.querySelector("input[data-publish-platform]:checked:not(:disabled)");
  if (checked && checked.dataset.publishPlatform) return checked.dataset.publishPlatform;
  return value("publishPlatform") || "douyin";
}

function setSelectedPublishPlatform(platform) {
  const nextPlatform = platform || "douyin";
  let matchedCardOption = false;
  for (const input of document.querySelectorAll("input[data-publish-platform]")) {
    if (input.disabled) continue;
    const checked = input.dataset.publishPlatform === nextPlatform;
    input.checked = checked;
    matchedCardOption = matchedCardOption || checked;
  }
  if (!matchedCardOption) {
    const douyin = $("agentPublishDouyin");
    if (douyin) douyin.checked = true;
  }
  const select = $("publishPlatform");
  if (select) select.value = matchedCardOption ? nextPlatform : "douyin";
}

function setupPublishPlatformSelection() {
  for (const input of document.querySelectorAll("input[data-publish-platform]")) {
    input.addEventListener("change", () => {
      if (input.disabled) return;
      if (input.checked) {
        setSelectedPublishPlatform(input.dataset.publishPlatform || "douyin");
      } else {
        setSelectedPublishPlatform("douyin");
      }
      state.publishAutomationStatus = null;
      renderPublishAutomationStatus();
    });
  }
  const select = $("publishPlatform");
  if (select) {
    select.addEventListener("change", () => {
      setSelectedPublishPlatform(select.value || "douyin");
      state.publishAutomationStatus = null;
      renderPublishAutomationStatus();
    });
  }
  setSelectedPublishPlatform(selectedPublishPlatform());
}

function setPublishAutomationBusy(isBusy) {
  state.publishAutomationRunning = Boolean(isBusy);
  for (const id of ["startPublishAutomationBtn", "agentPublishConfirmBtn", "agentPublishScheduleBtn"]) {
    const button = $(id);
    if (button) button.disabled = state.publishAutomationRunning;
  }
}

function renderPublishAutomationStatus(payload = null) {
  const box = $("publishAutomationStatusPanel");
  const platform = selectedPublishPlatform();
  const status = payload || state.publishAutomationStatus || {
    platform,
    status_label: "未开始",
    message: `点击发布后会打开${publishPlatformLabel(platform)}浏览器，首次使用请登录；登录态会保存在本机，下次无需重复登录。`,
    action_required: "start",
  };
  state.publishAutomationStatus = status;
  if (box) {
    box.innerHTML = "";
    const title = document.createElement("strong");
    title.textContent = `${publishPlatformLabel(status.platform)} · ${status.status_label || "未开始"}`;
    const message = document.createElement("span");
    message.textContent = status.message || "发布状态已更新。";
    const action = document.createElement("small");
    action.textContent =
      status.action_required === "confirm_final"
        ? "下一步：检查浏览器页面后点击确认发布。"
        : status.action_required === "login"
          ? "下一步：在浏览器中完成账号登录。"
          : status.action_required === "wait"
            ? "当前正在处理，请等待。"
            : `下一步：打开${publishPlatformLabel(status.platform)}发布页面。`;
    box.append(title, message, action);
  }
  const confirmButton = $("confirmPublishFinalBtn");
  if (confirmButton) confirmButton.disabled = status.action_required !== "confirm_final";
  const agentPublishButton = $("agentPublishConfirmBtn");
  if (agentPublishButton) agentPublishButton.disabled = state.publishAutomationRunning || status.action_required === "wait";
  const startButton = $("startPublishAutomationBtn");
  if (startButton) startButton.disabled = state.publishAutomationRunning;
  const kind = status.status === "failed" ? "error" : status.status === "published" ? "ok" : "warn";
  showAgentCardStatus("publish", status.message || `${publishPlatformLabel(status.platform)}浏览器辅助发布状态已更新。`, kind);
}

async function ensurePublishQueueForAutomation() {
  if (state.publishQueueId) return state.publishQueueId;
  await createPublishQueueItem();
  if (!state.publishQueueId) throw new Error("请先创建发布包。");
  return state.publishQueueId;
}

async function openPublishAccountLogin() {
  const platform = selectedPublishPlatform();
  const body = await api(`/publish/accounts/${encodeURIComponent(platform)}/open-login`, { method: "POST" });
  renderPublishAutomationStatus(body);
  log(body.message || `已打开${publishPlatformLabel(platform)}登录页。`, "ok");
}

async function startManualDouyinPublish() {
  const platform = selectedPublishPlatform();
  showAgentCardStatus("publish", `正在打开${publishPlatformLabel(platform)}浏览器。首次使用请在浏览器中登录，登录态会保存在本机。`, "warn");
  await startPublishAutomation();
}

async function startPublishAutomation() {
  const platform = selectedPublishPlatform();
  if (state.publishAutomationRunning) return;
  setPublishAutomationBusy(true);
  try {
    const queueId = await ensurePublishQueueForAutomation();
    const body = await api(`/publish/queue/${encodeURIComponent(queueId)}/automation/start`, { method: "POST" });
    renderPublishAutomationStatus(body);
    await refreshPublishConsole();
    log(body.message || `已启动${publishPlatformLabel(platform)}浏览器辅助发布。`, "ok");
  } finally {
    setPublishAutomationBusy(false);
  }
}

async function loadPublishAutomationStatus() {
  if (!state.publishQueueId) {
    renderPublishAutomationStatus();
    return;
  }
  const body = await api(`/publish/queue/${encodeURIComponent(state.publishQueueId)}/automation`);
  renderPublishAutomationStatus(body);
}

async function confirmPublishAutomationFinal() {
  if (!state.publishQueueId) throw new Error("请先创建发布包并点击发布。");
  const body = await api(`/publish/queue/${encodeURIComponent(state.publishQueueId)}/automation/confirm-final`, {
    method: "POST",
  });
  renderPublishAutomationStatus(body);
  await refreshPublishConsole();
  log(body.message || "已确认发布。", "ok");
}

async function schedulePublishAutomation() {
  switchView("publish-console");
  if (!value("publishScheduledAt")) {
    showAgentCardStatus("publish", "请先在任务与发布页填写排期时间，再启动定时发布。", "warn");
    throw new Error("请先填写排期时间。");
  }
  await startPublishAutomation();
}

async function handleAgentPublishButtonClick() {
  if (state.publishAutomationStatus?.action_required === "confirm_final") {
    await confirmPublishAutomationFinal();
    return;
  }
  await startManualDouyinPublish();
}

async function submitFeedback() {
  const rating = Number(value("feedbackRating") || 5);
  const message = value("feedbackMessage");
  if (!message) throw new Error("请先填写反馈内容。");
  const body = await api("/feedback", {
    method: "POST",
    body: JSON.stringify({
      rating,
      category: value("feedbackCategory") || "trial",
      message,
      contact: value("feedbackContact") || null,
    }),
  });
  writeJson("feedbackBox", body);
  setDownload("downloadFeedbackCsv", "/feedback/export.csv");
  await refreshFeedback();
  log(`反馈已提交：${body.feedback_id}`, "ok");
}

async function refreshFeedback() {
  const body = await api("/feedback");
  writeJson("feedbackBox", body);
  setDownload("downloadFeedbackCsv", "/feedback/export.csv");
}

async function refreshQualityDashboard() {
  const body = await api("/quality/dashboard");
  writeJson("qualityDashboard", body);
}

async function loadTaskQualitySummary() {
  requireTask();
  const body = await api(`/tasks/${state.taskId}/quality-summary`);
  writeJson("taskQualitySummary", body);
  log(`质量摘要已加载：${state.taskId}`, "ok");
}

async function runQualityBenchmark() {
  write("benchmarkReportBox", "正在运行基准测试。dry-run 会创建多条任务，请稍等。");
  const body = await api("/quality/benchmarks/run", {
    method: "POST",
    body: "{}",
  });
  state.benchmarkId = body.benchmark_id;
  writeJson("benchmarkReportBox", body);
  setDownload("downloadBenchmarkReport", body.download_url || `/quality/benchmarks/${state.benchmarkId}/download.json`);
  await refreshQualityDashboard();
  log(`基准测试完成：${state.benchmarkId}`, body.status === "completed" ? "ok" : "");
}

function renderJobs(jobs) {
  const box = $("jobList");
  if (!box) return;
  box.innerHTML = "";
  if (!jobs.length) {
    box.className = "list-box empty";
    box.textContent = "暂无排队任务";
    return;
  }
  box.className = "list-box";
  for (const job of jobs) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-row";
    const title = document.createElement("strong");
    title.textContent = `${job.kind} / ${job.status}`;
    const subtitle = document.createElement("span");
    subtitle.textContent = job.job_id;
    row.appendChild(title);
    row.appendChild(subtitle);
    row.onclick = () => selectJob(job);
    box.appendChild(row);
  }
}

function selectJob(job) {
  state.jobId = job.job_id;
  writeJson("jobDetails", job);
  safeRun(loadJobLogs);
}

async function loadCurrentTaskDetails(options = {}) {
  const taskId = value("currentTaskLookupId") || state.taskId;
  if (!taskId) throw new Error("请先创建视频任务，或粘贴任务 ID。");
  state.taskId = taskId;
  const task = await api(`/tasks/${state.taskId}`);
  setSourceVideoTaskRunning(task.status === "running");
  let progress = null;
  try {
    progress = await api(`/tasks/${state.taskId}/progress`);
  } catch (error) {
    progress = { error: error.message || String(error) };
  }
  writeJson("jobDetails", { task, progress });
  try {
    const text = await api(`/tasks/${state.taskId}/logs`);
    write("jobLogBox", text || "暂无日志。");
  } catch (error) {
    write("jobLogBox", error.message || "任务日志还未生成。");
  }
  if (task.status === "completed") enableDownloads();
  syncCurrentIds();
  if (!options.quiet) log(`当前任务已加载：${state.taskId}`, "ok");
}

async function refreshJobs() {
  const body = await api("/jobs");
  renderJobs(body.jobs || []);
  if (state.taskId) {
    try {
      await loadCurrentTaskDetails({ quiet: true });
    } catch (_error) {
      // The current task may have been deleted while the queue view stays open.
    }
  }
  if (state.jobId) {
    try {
      const job = await api(`/jobs/${state.jobId}`);
      writeJson("jobDetails", job);
    } catch (_error) {
      write("jobDetails", "选中的任务已经不存在。");
    }
  }
}

async function queueRenderJob() {
  requireTask();
  const body = await api(`/tasks/${state.taskId}/run-async`, {
    method: "POST",
    body: JSON.stringify({ max_retries: 1 }),
  });
  state.jobId = body.job_id;
  writeJson("jobDetails", body);
  await refreshJobs();
  log(`渲染任务已入队：${state.jobId}`, "ok");
}

async function queueCampaignJob() {
  if (!state.campaignId) await createCampaign();
  const body = await api(`/campaigns/${state.campaignId}/run-async`, {
    method: "POST",
    body: JSON.stringify({ max_retries: 1 }),
  });
  state.jobId = body.job_id;
  writeJson("jobDetails", body);
  await refreshJobs();
  log(`批量任务已入队：${state.jobId}`, "ok");
}

async function runNextJob() {
  const body = await api("/jobs/worker/run-next", {
    method: "POST",
    body: "{}",
  });
  state.jobId = body.job_id;
  writeJson("jobDetails", body);
  if (body.kind === "render_task" && body.payload && body.payload.task_id) {
    state.taskId = body.payload.task_id;
    if (body.status === "succeeded") enableDownloads();
  }
  if (body.kind === "campaign_run" && body.payload && body.payload.campaign_id) {
    state.campaignId = body.payload.campaign_id;
    await loadCampaignProgress();
  }
  await loadJobLogs();
  await refreshJobs();
  syncCurrentIds();
  log(`队列任务已处理：${state.jobId} / ${body.status}`, body.status === "succeeded" ? "ok" : "error");
}

async function retrySelectedJob() {
  if (!state.jobId) throw new Error("请先选择一个队列任务。");
  const body = await api(`/jobs/${state.jobId}/retry`, {
    method: "POST",
    body: "{}",
  });
  state.jobId = body.job_id;
  writeJson("jobDetails", body);
  await refreshJobs();
  log(`重试任务已入队：${state.jobId}`, "ok");
}

async function cancelSelectedJob() {
  if (!state.jobId) throw new Error("请先选择一个队列任务。");
  const body = await api(`/jobs/${state.jobId}/cancel`, {
    method: "POST",
    body: "{}",
  });
  writeJson("jobDetails", body);
  await loadJobLogs();
  await refreshJobs();
  log(`队列任务已取消：${state.jobId}`, "ok");
}

async function loadJobLogs() {
  if (!state.jobId) throw new Error("请先选择一个队列任务。");
  const text = await api(`/jobs/${state.jobId}/logs`);
  write("jobLogBox", text || "暂无日志。");
}

async function refreshReadiness() {
  const readiness = await api("/readiness");
  writeJson("readinessBox", readiness);
  write("healthBadge", readiness.status === "ok" ? "环境可用" : "需要检查");
  const badge = $("healthBadge");
  if (badge) badge.className = readiness.status === "ok" ? "ok" : "error";
  try {
    const probes = await api("/integrations/probes");
    writeJson("probeBox", probes);
  } catch (error) {
    write("probeBox", error.message || String(error));
  }
}

function isTextInputContextTarget(element) {
  if (!element || !(element instanceof HTMLElement)) return false;
  if (element.isContentEditable) return true;
  if (element.tagName === "TEXTAREA") return !element.disabled;
  if (element.tagName !== "INPUT") return false;
  const blockedTypes = new Set(["button", "checkbox", "color", "file", "hidden", "image", "radio", "range", "reset", "submit"]);
  const type = (element.getAttribute("type") || "text").toLowerCase();
  return !element.disabled && !blockedTypes.has(type);
}

function textInputContextTargetFromEvent(event) {
  const target = event.target && event.target.closest
    ? event.target.closest("input, textarea, [contenteditable='true'], [contenteditable='']")
    : event.target;
  return isTextInputContextTarget(target) ? target : null;
}

function hideTextInputContextMenu() {
  const menu = $("textInputContextMenu");
  if (!menu) return;
  menu.classList.add("hidden");
  menu.setAttribute("aria-hidden", "true");
}

function showTextInputContextMenu(x, y, target) {
  const menu = $("textInputContextMenu");
  if (!menu) return;
  activeTextInputContextTarget = target;
  menu.classList.remove("hidden");
  menu.setAttribute("aria-hidden", "false");
  const rect = menu.getBoundingClientRect();
  const left = Math.max(6, Math.min(x, window.innerWidth - rect.width - 6));
  const top = Math.max(6, Math.min(y, window.innerHeight - rect.height - 6));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function selectedTextFromContextTarget(target, requireSelection = false) {
  if (!target) return "";
  if (target.isContentEditable) {
    const selected = String(window.getSelection ? window.getSelection().toString() : "");
    return selected || (requireSelection ? "" : target.textContent || "");
  }
  const valueText = String(target.value || "");
  if (typeof target.selectionStart === "number" && typeof target.selectionEnd === "number") {
    const selected = valueText.slice(target.selectionStart, target.selectionEnd);
    return selected || (requireSelection ? "" : valueText);
  }
  return requireSelection ? "" : valueText;
}

function selectAllContextTargetText(target) {
  if (!target) return;
  target.focus();
  if (target.isContentEditable) {
    const range = document.createRange();
    range.selectNodeContents(target);
    const selection = window.getSelection();
    if (selection) {
      selection.removeAllRanges();
      selection.addRange(range);
    }
    return;
  }
  if (typeof target.select === "function") target.select();
}

function dispatchTextInputContextEvents(target) {
  target.dispatchEvent(new Event("input", { bubbles: true }));
  target.dispatchEvent(new Event("change", { bubbles: true }));
}

function replaceContextTargetSelection(target, text) {
  if (!target || target.readOnly || target.disabled) return;
  target.focus();
  if (target.isContentEditable) {
    document.execCommand("insertText", false, text);
    dispatchTextInputContextEvents(target);
    return;
  }
  if (typeof target.selectionStart === "number" && typeof target.selectionEnd === "number" && typeof target.setRangeText === "function") {
    target.setRangeText(text, target.selectionStart, target.selectionEnd, "end");
  } else {
    target.value = `${target.value || ""}${text}`;
  }
  dispatchTextInputContextEvents(target);
}

function fallbackWriteClipboardText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

async function writeContextClipboardText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  fallbackWriteClipboardText(text);
}

async function readContextClipboardText() {
  if (navigator.clipboard && navigator.clipboard.readText) {
    return navigator.clipboard.readText();
  }
  return "";
}

async function handleTextInputContextAction(action) {
  const target = activeTextInputContextTarget;
  hideTextInputContextMenu();
  if (!isTextInputContextTarget(target)) return;
  if (action === "select-all") {
    selectAllContextTargetText(target);
    return;
  }
  if (action === "copy") {
    await writeContextClipboardText(selectedTextFromContextTarget(target));
    return;
  }
  if (action === "cut") {
    const selected = selectedTextFromContextTarget(target, true);
    if (!selected || target.readOnly || target.disabled) return;
    await writeContextClipboardText(selected);
    replaceContextTargetSelection(target, "");
    return;
  }
  if (action === "paste") {
    const text = await readContextClipboardText();
    if (text) replaceContextTargetSelection(target, text);
  }
}

function bindTextInputContextMenu() {
  if (textInputContextMenuBound) return;
  textInputContextMenuBound = true;
  document.addEventListener("contextmenu", (event) => {
    const target = textInputContextTargetFromEvent(event);
    if (!target) {
      hideTextInputContextMenu();
      return;
    }
    event.preventDefault();
    showTextInputContextMenu(event.clientX, event.clientY, target);
  });
  document.addEventListener("click", (event) => {
    const menu = $("textInputContextMenu");
    if (menu && menu.contains(event.target)) return;
    hideTextInputContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideTextInputContextMenu();
  });
  window.addEventListener("resize", hideTextInputContextMenu);
  window.addEventListener("scroll", hideTextInputContextMenu, true);
  const menu = $("textInputContextMenu");
  if (!menu) return;
  for (const button of menu.querySelectorAll("[data-text-input-action]")) {
    button.onclick = () => safeRun(() => handleTextInputContextAction(button.dataset.textInputAction));
  }
}

async function safeRun(fn) {
  try {
    await fn();
  } catch (error) {
    log(error.message || String(error), "error");
  }
}

function bindClick(id, fn) {
  const button = $(id);
  if (button) button.onclick = () => safeRun(fn);
}

function bindChange(id, fn) {
  const element = $(id);
  if (element) element.onchange = fn;
}

function bindInput(id, fn) {
  const element = $(id);
  if (element) element.oninput = fn;
}

function bind() {
  bindTextInputContextMenu();
  bindSourceVideoDropZone();
  for (const button of document.querySelectorAll("[data-nav]")) {
    button.onclick = () => switchView(button.dataset.nav);
  }
  for (const button of document.querySelectorAll("[data-go]")) {
    button.onclick = () => switchView(button.dataset.go);
  }
  bindClick("refreshModelsBtn", refreshModelCenter);
  bindClick("applyModelPresetBtn", applyModelPreset);
  bindClick("validateModelSelectionBtn", validateModelSelection);
  bindClick("saveModelSelectionBtn", saveModelSelection);
  bindClick("loadModelSelectionBtn", loadModelSelection);
  bindClick("saveDigitalHumanProviderConfigBtn", saveDigitalHumanProviderConfig);
  bindClick("checkDigitalHumanProviderConfigBtn", checkDigitalHumanProviderConfig);
  bindClick("saveObjectStorageConfigBtn", saveObjectStorageConfig);
  bindClick("checkObjectStorageConfigBtn", checkObjectStorageConfig);
  bindChange("digitalHumanProviderSelect", () => {
    if (state.desktopSettings) setDigitalHumanProviderFields(state.desktopSettings);
  });
  bindChange("digitalHumanModelSelect", () => {
    syncDigitalHumanProviderSelect();
    if (state.desktopSettings) setDigitalHumanProviderFields(state.desktopSettings);
  });
  bindChange("objectStorageBackendSelect", markObjectStorageConfigDirty);
  const providerBaseUrlInput = $("digitalHumanProviderBaseUrl");
  if (providerBaseUrlInput) providerBaseUrlInput.oninput = markDigitalHumanProviderConfigDirty;
  const providerApiKeyInput = $("digitalHumanProviderApiKey");
  if (providerApiKeyInput) providerApiKeyInput.oninput = markDigitalHumanProviderConfigDirty;
  for (const inputId of [
    "objectStoragePublicBaseUrl",
    "objectStorageBucket",
    "objectStorageEndpointOrRegion",
    "objectStorageAccessKeyId",
    "objectStorageSecretAccessKey",
  ]) {
    const input = $(inputId);
    if (input) input.oninput = markObjectStorageConfigDirty;
  }
  bindClick("openLlmSettingsBtn", openLlmSettings);
  bindClick("addLocalLlmModelBtn", openLocalLlmModelModal);
  bindClick("closeDigitalHumanPreviewBtn", () => showModal("digitalHumanPreviewModal", false));
  bindClick("closeLlmSettingsBtn", () => showModal("llmSettingsModal", false));
  bindClick("closeLocalLlmModelBtn", () => showModal("localLlmModelModal", false));
  bindClick("saveLlmPlatformsBtn", saveLlmPlatforms);
  bindClick("checkLlmPlatformBtn", checkLlmPlatform);
  bindClick("refreshLlmModelsBtn", refreshLlmModels);
  bindClick("addLlmModelBtn", addLlmModel);
  bindClick("saveLocalLlmModelBtn", saveLocalLlmModel);
  const platformSearch = $("llmPlatformSearch");
  if (platformSearch) platformSearch.oninput = renderLlmPlatformList;
  bindClick("refreshProjectsBtn", refreshProjects);
  bindClick("refreshCloneAvatarBtn", refreshSourceVideoHumans);
  bindClick("refreshCloneAvatarInlineBtn", refreshSourceVideoHumans);
  bindClick("refreshHumansBtn", refreshDigitalHumans);
  bindClick("refreshVoicesBtn", refreshVoiceProfiles);
  bindClick("refreshVoicesInlineBtn", refreshVoiceProfiles);
  bindClick("refreshReadinessBtn", refreshReadiness);
  bindClick("humanReadinessBtn", refreshHumanReadiness);
  bindClick("refreshRoleModelsBtn", refreshRoleModels);
  bindClick("createRoleModelBtn", createRoleModel);
  bindClick("selectRoleModelBtn", selectRoleModel);
  bindClick("validateRoleModelBtn", validateRoleModel);
  const sourceVideoHumanSelect = $("sourceVideoHumanSelect");
  if (sourceVideoHumanSelect) {
    sourceVideoHumanSelect.onchange = () => {
      state.digitalHumanId = value("sourceVideoHumanSelect");
      safeRun(async () => {
        await refreshSourceVideoVoices();
        await loadSourceVideoAssetPreview();
      });
      updateSourceVideoHumanFilterControls();
      syncCurrentIds();
    };
  }
  const sourceVideoVoiceSelect = $("sourceVideoVoiceSelect");
  if (sourceVideoVoiceSelect) {
    sourceVideoVoiceSelect.onchange = () => {
      state.voiceProfileId = value("sourceVideoVoiceSelect");
      safeRun(loadSourceVideoAssetPreview);
      syncCurrentIds();
    };
  }
  const sourceVideoOnlyReadyHumans = $("sourceVideoOnlyReadyHumans");
  if (sourceVideoOnlyReadyHumans) sourceVideoOnlyReadyHumans.onchange = () => safeRun(refreshSourceVideoHumans);
  const remixMainVideoFile = $("remixMainVideoFile");
  if (remixMainVideoFile) {
    remixMainVideoFile.onchange = () => {
      const file = remixMainVideoFile.files && remixMainVideoFile.files[0];
      if (!file) return;
      state.selectedRemixMainVideoPath = "";
      state.selectedRemixMainVideoScript = "";
      if ($("remixMainVideoSelect")) $("remixMainVideoSelect").value = "";
      for (const card of document.querySelectorAll(".remix-video-card")) card.classList.remove("selected");
      clearRemixMainVideoPreview(`已选择本地成片视频：${file.name}`);
      write("remixMainVideoName", file.name);
      if ($("remixSubtitleText")) $("remixSubtitleText").placeholder = "本地上传成片没有原脚本；需要字幕时可手动填写";
    };
  }
  const remixAssetFiles = $("remixAssetFiles");
  if (remixAssetFiles) {
    remixAssetFiles.onchange = () => renderRemixAssetPreview(remixAssetFiles.files);
  }
  const sourceVideoPipAssetFiles = $("sourceVideoPipAssetFiles");
  if (sourceVideoPipAssetFiles) {
    sourceVideoPipAssetFiles.onchange = () => {
      addSourceVideoPipAssetFiles(sourceVideoPipAssetFiles.files);
      sourceVideoPipAssetFiles.value = "";
    };
  }
  bindClick("showAllSourceVideoHumansBtn", showAllSourceVideoHumans);
  bindClick("hideSourceVideoHumanBtn", hideCurrentSourceVideoHuman);
  bindClick("deleteSourceVideoHumanBtn", deleteSourceVideoHuman);
  bindClick("cleanupEmptySourceVideoHumansBtn", cleanupEmptySourceVideoHumans);
  bindClick("clearAllSourceVideoHumansBtn", clearAllSourceVideoHumans);
  bindClick("refreshSourceVideoAssetPreviewBtn", loadSourceVideoAssetPreview);
  bindClick("playSourceVideoVoiceBtn", previewSourceVideoVoice);
  bindInput("sourceVideoIpInput", updateSourceVideoTextCounters);
  bindInput("sourceVideoScript", updateSourceVideoTextCounters);
  bindChange("sourceVideoLanguage", () => safeRun(syncSourceVideoScriptLanguage));
  bindChange("sourceVideoMoodSelect", syncSourceVideoVoiceControls);
  bindInput("sourceVideoSpeechRate", syncSourceVideoVoiceControls);
  bindClick("sourceVideoReferenceLinkAnalyzeBtn", transcribeSourceVideoReferenceLink);
  bindClick("sourceVideoDownloadWatchBtn", startSourceVideoReferenceDownloadWatch);
  bindClick("agentAutoModeBtn", runAgentAutoMode);
  bindClick("themeToggleBtn", toggleStudioTheme);
  bindClick("desktopLicenseActivateBtn", activateDesktopLicense);
  bindClick("desktopLicenseRefreshBtn", refreshDesktopLicenseStatus);
  bindClick("desktopLicenseDeactivateBtn", deactivateDesktopLicense);
  bindClick("creditBalanceBtn", openCreditUsageDialog);
  bindClick("closeCreditUsageBtn", () => setCreditUsageDialogVisible(false));
  const creditUsageDialog = $("creditUsageDialog");
  if (creditUsageDialog) {
    creditUsageDialog.onclick = (event) => {
      if (event.target === creditUsageDialog) setCreditUsageDialogVisible(false);
    };
  }
  const desktopLicenseKeyInput = $("desktopLicenseKeyInput");
  if (desktopLicenseKeyInput) {
    desktopLicenseKeyInput.onkeydown = (event) => {
      if (event.key === "Enter") safeRun(activateDesktopLicense);
    };
  }
  bindClick("sourceVideoPrepareBtn", sourceVideoPrepareProfile);
  bindClick("sourceVideoSaveScriptBtn", () => applySourceVideoScriptAction("rewrite"));
  bindClick("sourceVideoRenderBtn", renderSourceVideoTask);
  bindClick("sourceVideoReportBtn", loadSourceVideoReport);
  bindClick("sourceVideoPipSettingsBtn", toggleSourceVideoPipSettings);
  bindClick("closeSourceVideoPipModalBtn", closeSourceVideoPipModal);
  bindClick("confirmSourceVideoPipAssetsBtn", closeSourceVideoPipModal);
  bindClick("sourceVideoPipPickMoreBtn", pickMoreSourceVideoPipAssets);
  bindClick("sourceVideoPipClearAssetsBtn", clearSourceVideoPipAssets);
  bindClick("sourceVideoPipGenerateBtn", createSourceVideoPipRemixTask);
  bindChange("sourceVideoPipEnabled", () => {
    if (checked("sourceVideoPipEnabled")) {
      openSourceVideoPipModal();
    } else {
      closeSourceVideoPipModal();
      showAgentCardStatus("edit", "画中画已关闭，生成时不会插入素材。", "warn");
    }
  });
  bindClick("sourceVideoGenerateTagsBtn", generateSourceVideoTitleTagsWithCloud);
  bindClick("sourceVideoCoverSettingsBtn", openCoverSettingsModal);
  bindClick("closeCoverSettingsBtn", closeCoverSettingsModal);
  bindClick("confirmCoverTemplateBtn", closeCoverSettingsModal);
  bindClick("sourceVideoCoverPreviewImage", openCoverPreviewModal);
  bindClick("closeCoverPreviewBtn", closeCoverPreviewModal);
  bindClick("sourceVideoImportCoverBtn", chooseLocalCoverImage);
  bindChange("sourceVideoCoverImportFile", importLocalCoverImage);
  bindClick("sourceVideoGenerateCoverBtn", generateSourceVideoCover);
  const sourceVideoCoverPreviewImage = $("sourceVideoCoverPreviewImage");
  if (sourceVideoCoverPreviewImage) sourceVideoCoverPreviewImage.onkeydown = handleCoverPreviewKeydown;
  const coverPreviewModal = $("coverPreviewModal");
  if (coverPreviewModal) {
    coverPreviewModal.onclick = (event) => {
      if (event.target === coverPreviewModal) closeCoverPreviewModal();
    };
  }
  bindClick("sourceVideoPreviewBgmBtn", previewSelectedBgm);
  bindClick("sourceVideoBgmPickerBtn", openBgmPickerModal);
  bindClick("closeSourceVideoBgmModalBtn", closeBgmPickerModal);
  bindClick("sourceVideoBgmModalPreviewBtn", previewSelectedBgm);
  bindClick("sourceVideoAddBgmBtn", createSourceVideoBgmFinalTask);
  bindChange("sourceVideoBgmSelect", () => {
    state.selectedBgmId = value("sourceVideoBgmSelect");
    updateBgmPreview(false);
  });
  bindBgmNativeVolumeControl();
  bindChange("sourceVideoBgmEnabled", () => {
    const enabled = checked("sourceVideoBgmEnabled");
    showAgentCardStatus("subtitle", enabled ? "背景音乐已启用，导出最终结果时会混入成片。" : "背景音乐已关闭，最终结果会保留卡片 03 的原声。", enabled ? "ok" : "warn");
  });
  const sourceVideoBgmModalList = $("sourceVideoBgmModalList");
  if (sourceVideoBgmModalList) {
    sourceVideoBgmModalList.onclick = handleBgmPickerAction;
  }
  const sourceVideoBgmModal = $("sourceVideoBgmModal");
  if (sourceVideoBgmModal) {
    sourceVideoBgmModal.onclick = (event) => {
      if (event.target === sourceVideoBgmModal) closeBgmPickerModal();
    };
  }
  bindInlineSourceVideoScriptActions();
  bindClick("refreshReferencesBtn", refreshReferences);
  bindClick("createReferenceBtn", createReference);
  bindClick("selectReferenceBtn", selectReference);
  bindClick("analyzeReferenceBtn", analyzeReference);
  bindClick("loadReferenceAnalysisBtn", loadReferenceAnalysis);
  bindClick("generateScriptsBtn", generateScripts);
  bindClick("generateCopyBtn", generateCopyScripts);
  bindClick("pasteCopyBtn", pasteCopyInput);
  bindClick("clearCopyBtn", clearCopyInput);
  bindChange("rewriteProductInfo", updateRewriteInputCount);
  bindChange("rewriteStyle", () => {
    syncRewriteStyleTone();
    updateRewriteInputCount();
  });
  const rewriteInput = $("rewriteProductInfo");
  if (rewriteInput) rewriteInput.oninput = updateRewriteInputCount;
  syncRewriteStyleTone();
  updateRewriteInputCount();
  bindClick("refreshRewritesBtn", refreshRewrites);
  bindClick("selectScriptForTaskBtn", selectScriptForTask);
  bindClick("createCampaignBtn", createCampaign);
  bindClick("runCampaignBtn", () => runCampaign(false));
  bindClick("campaignProgressBtn", loadCampaignProgress);
  bindClick("retryCampaignBtn", () => runCampaign(true));
  bindChange("campaignCsvFile", () => safeRun(loadCampaignCsvFile));
  bindClick("refreshPublishBoardBtn", refreshPublishConsole);
  bindClick("createPublishQueueBtn", createPublishQueueItem);
  bindClick("updatePublishStatusBtn", updatePublishStatus);
  bindClick("loadPublishCalendarBtn", loadPublishCalendar);
  bindClick("openPublishAccountLoginBtn", openPublishAccountLogin);
  bindClick("openPublishAccountLoginQuickBtn", openPublishAccountLogin);
  bindClick("startPublishAutomationBtn", startPublishAutomation);
  bindClick("agentPublishScheduleBtn", schedulePublishAutomation);
  bindClick("refreshPublishAutomationBtn", loadPublishAutomationStatus);
  bindClick("confirmPublishFinalBtn", confirmPublishAutomationFinal);
  bindClick("agentPublishConfirmBtn", handleAgentPublishButtonClick);
  setupPublishPlatformSelection();
  renderPublishAutomationStatus();
  bindClick("refreshFeedbackBtn", refreshFeedback);
  bindClick("submitFeedbackBtn", submitFeedback);
  bindClick("refreshQualityBtn", refreshQualityDashboard);
  bindClick("loadTaskQualityBtn", loadTaskQualitySummary);
  bindClick("runBenchmarkBtn", runQualityBenchmark);
  bindClick("refreshJobsBtn", refreshJobs);
  bindClick("queueRenderJobBtn", queueRenderJob);
  bindClick("queueCampaignJobBtn", queueCampaignJob);
  bindClick("runNextJobBtn", runNextJob);
  bindClick("retryJobBtn", retrySelectedJob);
  bindClick("cancelJobBtn", cancelSelectedJob);
  bindClick("loadCurrentTaskBtn", loadCurrentTaskDetails);
  bindClick("loadJobLogsBtn", loadJobLogs);
  bindClick("createProjectBtn", createProject);
  bindClick("selectProjectBtn", selectProject);
  bindClick("createHumanBtn", createDigitalHuman);
  bindClick("uploadPersonalHumanBtn", uploadPersonalDigitalHuman);
  bindClick("selectHumanBtn", selectDigitalHuman);
  bindClick("generateAvatarBtn", generateAvatar);
  bindClick("selectAvatarBtn", selectAvatar);
  bindClick("createVoiceBtn", createVoiceProfile);
  bindClick("selectVoiceBtn", selectVoiceProfile);
  bindClick("playVoiceSampleBtn", playVoiceSample);
  bindClick("testVoiceBtn", testVoice);
  bindClick("deleteVoiceInlineBtn", deleteVoiceProfile);
  bindClick("createTaskBtn", createVideoTask);
  bindChange("videoTemplateSelect", previewVideoTemplate);
  bindClick("refreshRemixMainVideosBtn", refreshVideoRemixMainVideos);
  bindClick("videoRemixGenerateBtn", createVideoRemixTask);
  for (const button of document.querySelectorAll("[data-remix-count]")) {
    button.onclick = () => setVideoRemixCount(button.dataset.remixCount);
  }
  bindAgentFailureButtons();
  setVideoRemixCount(state.remixOutputCount);
  updateSourceVideoTextCounters();
  bindClick("generateScriptBtn", generateScript);
  bindClick("generateScriptQuickBtn", generateScript);
  bindClick("renderBtn", renderVideo);
  bindClick("generateFinalBtn", renderVideo);
  bindClick("renderQuickBtn", renderVideo);
  bindClick("reviewBtn", reviewScript);
  bindClick("progressBtn", trackProgress);
  bindClick("previewBtn", previewResults);
}

async function boot() {
  bind();
  setDesktopLicenseGateVisible(true);
  await refreshDesktopLicenseStatus();
  state.projectId = value("projectId") || "project_demo";
  syncCurrentIds();
  try {
    await refreshReadiness();
  } catch (error) {
    write("healthBadge", "需要检查");
    const badge = $("healthBadge");
    if (badge) badge.className = "error";
    log(error.message || String(error), "error");
  }
  await safeRun(refreshProjects);
  await safeRun(refreshVideoTemplates);
  await safeRun(loadBgmLibrary);
  await safeRun(loadCoverTemplates);
  await safeRun(refreshSourceVideoHumans);
}

document.addEventListener("DOMContentLoaded", boot);
