<template>
  <div>
    <!-- 页头 -->
    <div style="text-align:center;padding:32px 0 8px">
      <h1 style="font-size:24px;font-weight:800;color:#1a1a2e">数字人内容生成工作流</h1>
      <p style="color:#888;font-size:13px;margin-top:6px">
        按顺序完成内容、文本、形象语音和数字人口播视频生成
      </p>
    </div>

    <div class="task-picker">
      <label>任务 ID</label>
      <select
        v-model="selectedSessionId"
        :disabled="sessionLoading || !taskSessions.length"
        @change="loadSelectedSession"
      >
        <option value="">选择历史任务</option>
        <option
          v-for="task in taskSessions"
          :key="task.session_id"
          :value="task.session_id"
        >
          {{ formatTaskOption(task) }}
        </option>
      </select>
      <button class="btn btn-outline" :disabled="sessionLoading" @click="refreshSessions">
        刷新
      </button>
      <button
        class="btn btn-primary"
        :disabled="sessionLoading || !selectedSessionId"
        @click="loadSelectedSession"
      >
        {{ sessionLoading ? '读取中…' : '打开任务' }}
      </button>
    </div>

    <!-- 步骤指示器 -->
    <div class="stepper">
      <div
        v-for="(s, i) in STEPS"
        :key="s.key"
        class="step-item"
        :class="{
          active: currentStep === i,
          done: isStepDone(i),
          clickable: canVisitStep(i),
          locked: !canVisitStep(i),
        }"
        :title="getStepHint(i)"
        @click="goToStep(i)"
      >
        <div class="step-dot">
          <span v-if="isStepDone(i)">✓</span>
          <span v-else>{{ i + 1 }}</span>
        </div>
        <div class="step-label">{{ s.label }}</div>
      </div>
    </div>
    <p class="stepper-tip">
      需要从第一步开始按顺序完成；可返回已完成步骤查看或修改。
    </p>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-error">
      <span>⚠️</span>
      <span>{{ error }}</span>
    </div>

    <!-- ── 步骤 0：提取内容 ──────────────────────────── -->
    <div v-if="currentStep === 0" class="card">
      <div class="card-title">
        <span>📥 提取内容</span>
        <span class="badge">步骤 1</span>
      </div>

      <!-- 来源切换 -->
      <div class="tabs">
        <button
          class="tab-btn"
          :class="{ active: sourceMode === 'url' }"
          @click="sourceMode = 'url'"
        >🔗 网页链接</button>
        <button
          class="tab-btn"
          :class="{ active: sourceMode === 'file' }"
          @click="sourceMode = 'file'"
        >🎬 视频文件</button>
      </div>

      <!-- URL 输入 -->
      <template v-if="sourceMode === 'url'">
        <div class="input-group">
          <label>网页 URL</label>
          <input
            v-model="urlInput"
            type="url"
            placeholder="https://example.com/article"
          />
        </div>
      </template>

      <!-- 文件上传 -->
      <template v-else>
        <div
          class="upload-area"
          :class="{ 'drag-over': isDragOver }"
          @click="$refs.fileInput.click()"
          @dragover.prevent="isDragOver = true"
          @dragleave="isDragOver = false"
          @drop.prevent="onDrop"
        >
          <input ref="fileInput" type="file" accept="video/*" @change="onFileChange" />
          <div class="upload-icon">🎬</div>
          <div v-if="selectedFile" class="upload-name">{{ selectedFile.name }}</div>
          <p v-else>点击选择或拖拽视频文件<br><small>支持 MP4 / MOV / AVI / MKV 等</small></p>
        </div>
      </template>

      <div class="btn-row">
        <button
          class="btn btn-primary"
          :disabled="loading || (sourceMode === 'url' ? !urlInput.trim() : !selectedFile)"
          @click="handleExtract"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '提取中…' : '开始提取' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 1：改写文本 ──────────────────────────── -->
    <div v-if="currentStep === 1" class="card">
      <div class="card-title">
        <span>✏️ AI 改写</span>
        <span class="badge">步骤 2</span>
      </div>

      <!-- 原文预览 -->
      <div class="input-group">
        <label>原始提取文本</label>
        <div class="result-box">{{ extractedText }}</div>
      </div>

      <!-- 改写风格选择 -->
      <div class="input-group">
        <label>选择改写风格</label>
        <div class="style-grid">
          <div
            v-for="s in rewriteStyles"
            :key="s.style_id"
            class="style-card"
            :class="{ selected: selectedStyle === s.style_id }"
            @click="selectedStyle = s.style_id"
          >
            <div class="style-icon">{{ STYLE_ICONS[s.style_id] || '📝' }}</div>
            <div class="style-name">{{ s.display_name }}</div>
          </div>
        </div>
      </div>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 0">← 重新提取</button>
        <button class="btn btn-outline" @click="goToStep(2)">直接确认文本</button>
        <button
          class="btn btn-primary"
          :disabled="loading || !selectedStyle"
          @click="handleRewrite"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '改写中…' : 'AI 改写' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 2：确认文本 ──────────────────────────── -->
    <div v-if="currentStep === 2" class="card">
      <div class="card-title">
        <span>✅ 确认文本</span>
        <span class="badge">步骤 3</span>
      </div>

      <div class="input-group">
        <label>待确认文本（可直接确认或先编辑修改）</label>
        <textarea
          v-model="editableText"
          class="result-box editable"
          rows="10"
          style="border:1.5px solid #ddd;"
        ></textarea>
      </div>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 1">← 重新改写</button>
        <button
          class="btn btn-success"
          :disabled="loading || !editableText.trim()"
          @click="handleConfirm"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '保存中…' : '确认文本' }}</span>
        </button>
      </div>
    </div>

    <!-- ── 步骤 3：准备形象与语音 ────────────────── -->
    <div v-if="currentStep === 3" class="card">
      <div class="card-title">
        <span>🖼️ 准备形象与语音</span>
        <span class="badge">步骤 4</span>
      </div>

      <div class="input-group">
        <label>数字人参考图</label>
        <div class="upload-area" @click="$refs.avatarImageInput.click()">
          <input ref="avatarImageInput" type="file" accept="image/png,image/jpeg,image/webp" @change="onAvatarImageChange" />
          <template v-if="avatarPreviewUrl">
            <img :src="avatarPreviewUrl" alt="avatar preview" class="avatar-preview" />
            <div class="upload-name">{{ avatarImageFile ? avatarImageFile.name : '已选择图片' }}</div>
          </template>
          <template v-else>
            <div class="upload-icon">🖼️</div>
            <p>点击上传人物图片<br><small>支持 PNG / JPG / JPEG / WebP</small></p>
          </template>
        </div>
      </div>

      <div class="input-group">
        <label>待播报文本</label>
        <div class="result-box">{{ finalText }}</div>
      </div>

      <template v-if="audioUrl">
        <div class="alert alert-success">✅ 音频生成成功</div>
        <audio :src="audioUrl" controls></audio>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 2">← 修改文本</button>
        <button v-if="!audioUrl" class="btn btn-primary" :disabled="loading" @click="handleAudio">
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '生成中…' : '生成语音' }}</span>
        </button>
        <template v-if="audioUrl">
          <button class="btn btn-primary" :disabled="loading" @click="proceedToVideoStep">
            <span v-if="loading" class="spinner"></span>
            <span>{{ loading ? '保存图片中…' : '普通口播 →' }}</span>
          </button>
          <button
            class="btn btn-success"
            :disabled="storyboardLoading || !hasAvatarImage()"
            @click="enterStoryboardMode"
          >
            <span v-if="storyboardLoading" class="spinner"></span>
            <span>{{ storyboardLoading ? '初始化中…' : '🎬 分镜模式' }}</span>
          </button>
        </template>
      </div>
    </div>

    <!-- ── 步骤 5：生成视频 ───────────────────────────── -->
    <div v-if="currentStep === 4" class="card">
      <div class="card-title">
        <span>🤖 数字人口播视频</span>
        <span class="badge">步骤 5</span>
      </div>

      <!-- 服务商选择 -->
      <template v-if="!videoUrl">
        <div class="input-group">
          <label>数字人服务商</label>
          <div class="tabs">
            <button
              class="tab-btn"
              :class="{ active: videoProvider === 'kling' }"
              :disabled="videoStatus === 'queued' || videoStatus === 'processing'"
              @click="videoProvider = 'kling'"
            >⚡ 可灵</button>
            <button
              class="tab-btn"
              :class="{ active: videoProvider === 'baidu' }"
              :disabled="videoStatus === 'queued' || videoStatus === 'processing'"
              @click="videoProvider = 'baidu'"
            >🔵 百度云</button>
          </div>
        </div>
      </template>

      <template v-if="videoUrl">
        <div class="alert alert-success">🎉 视频生成成功！（服务商：{{ videoProvider === 'baidu' ? '百度云' : '可灵' }}）</div>
        <video
          class="video-preview"
          :src="videoUrl"
          controls
          playsinline
          preload="metadata"
        ></video>
        <a :href="videoUrl" target="_blank" rel="noopener" class="video-link">
          🎬 新窗口打开 / 下载视频
        </a>
      </template>
      <template v-else>
        <div v-if="videoStatus === 'queued' || videoStatus === 'processing'" class="alert alert-info">
          ⏳ 视频正在后台生成，可点击下方"刷新状态"按钮查询最新进度。
        </div>
        <div v-else-if="videoStatus === 'failed'" class="alert alert-error">
          生成失败：{{ videoError || '服务未返回明确错误信息' }}
        </div>
        <!-- 失败时显示补录区（轮询超时任务可能仍在云端运行） -->
        <template v-if="videoStatus === 'failed'">
          <div class="input-group" style="margin-top:8px">
            <label>{{ videoProvider === 'kling' ? '补录可灵 task_id' : '补录百度云 task_id' }}（任务超时后用此查询实际结果）</label>
            <div style="display:flex;gap:8px">
              <input
                v-model="patchTaskId"
                type="text"
                :placeholder="videoProvider === 'kling' ? '888509099301298195' : 'img-xxxxxxxxxxxxxxxx'"
                style="flex:1"
              />
              <button
                class="btn btn-primary"
                :disabled="patchLoading || !patchTaskId.trim()"
                @click="handleVideoPatch"
              >
                <span v-if="patchLoading" class="spinner"></span>
                <span>{{ patchLoading ? '查询中…' : '查询并补录' }}</span>
              </button>
            </div>
          </div>
        </template>
        <div class="alert alert-info">
          ⚡ 数字人口播生成通常需要 1-3 分钟，提交任务后会异步处理，避免接口超时。
        </div>
        <div v-if="videoProvider === 'kling'" class="alert alert-info" style="margin-top:0">
          ⚙️ 可灵：需要在 .env 中配置 KLING_ACCESS_KEY_ID / KLING_ACCESS_KEY_SECRET
        </div>
        <div v-else class="alert alert-info" style="margin-top:0">
          ⚙️ 百度云：需要在 .env 中配置 BAIDU_DH_APP_ID / BAIDU_DH_APP_KEY / COS_SECRET_ID / COS_SECRET_KEY / COS_BUCKET / COS_REGION
        </div>
      </template>

      <div class="btn-row">
        <button class="btn btn-outline" @click="currentStep = 3">← 返回</button>
        <button
          v-if="videoStatus === 'queued' || videoStatus === 'processing'"
          class="btn btn-outline"
          :disabled="refreshLoading"
          @click="handleRefreshVideoStatus"
        >
          <span v-if="refreshLoading" class="spinner"></span>
          <span>{{ refreshLoading ? '查询中…' : '刷新状态' }}</span>
        </button>
        <button
          v-if="!videoUrl && videoStatus !== 'queued' && videoStatus !== 'processing'"
          class="btn btn-primary"
          :disabled="loading"
          @click="handleVideo"
        >
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? '提交中…' : (videoStatus === 'failed' ? '重新生成数字人视频' : '提交生成数字人视频') }}</span>
        </button>
        <button v-if="videoUrl" class="btn btn-success" @click="reset">🔄 重新开始</button>
      </div>
    </div>

    <!-- ── 分镜模式面板 ─────────────────────────────────── -->
    <div v-if="storyboardMode" class="card">
      <div class="card-title">
        <span>🎬 分镜模式</span>
        <span class="badge">{{ storyboardSuccessCount }}/{{ storyboardScenes.length }} 完成</span>
      </div>

      <!-- 控制栏 -->
      <div class="btn-row" style="margin-bottom:12px">
        <button class="btn btn-outline" @click="exitStoryboardMode">← 退出分镜</button>
        <button
          class="btn btn-primary"
          :disabled="storyboardLoading || storyboardStatus === 'processing'"
          @click="handleGenerateAll"
        >
          <span v-if="storyboardStatus === 'processing'" class="spinner"></span>
          <span>{{ storyboardStatus === 'processing' ? '生成中…' : '全部生成' }}</span>
        </button>
        <button
          v-if="storyboardSuccessCount === storyboardScenes.length && storyboardScenes.length > 0"
          class="btn btn-success"
          :disabled="storyboardMerging || !!storyboardMergedUrl"
          @click="handleMerge"
        >
          <span v-if="storyboardMerging" class="spinner"></span>
          <span>{{ storyboardMerging ? '合并中…' : storyboardMergedUrl ? '已合并' : '合并视频' }}</span>
        </button>
      </div>

      <!-- 合并结果 -->
      <template v-if="storyboardMergedUrl">
        <div class="alert alert-success">🎉 合并完成！</div>
        <video class="video-preview" :src="storyboardMergedUrl" controls playsinline preload="metadata"></video>
        <a :href="storyboardMergedUrl" target="_blank" rel="noopener" class="video-link">🎬 下载合并视频</a>
      </template>

      <!-- 场景列表 -->
      <div
        v-for="scene in storyboardScenes"
        :key="scene.index"
        style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:12px"
      >
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <strong>场景 {{ scene.index + 1 }}</strong>
          <span :style="{
            color: scene.video_status === 'succeed' ? '#16a34a'
                 : scene.video_status === 'failed'  ? '#dc2626'
                 : '#d97706',
            fontSize: '12px'
          }">
            {{ { pending:'等待', processing:'生成中…', succeed:'✓ 完成', failed:'✗ 失败' }[scene.video_status] || scene.video_status }}
          </span>
        </div>

        <!-- 文案 -->
        <div style="font-size:13px;color:#444;margin-bottom:8px;background:#f9f9f9;padding:6px 8px;border-radius:4px">
          {{ scene.text }}
        </div>

        <!-- 分镜图 -->
        <div v-if="scene.image_status === 'succeed' && scene.image_url" style="margin-bottom:8px">
          <img :src="scene.image_url" alt="分镜图" style="max-width:100%;max-height:200px;border-radius:4px;border:1px solid #ddd" />
        </div>
        <div v-else-if="scene.image_status === 'failed'" style="font-size:12px;color:#dc2626;margin-bottom:4px">
          图片失败：{{ scene.image_error }}
        </div>

        <!-- 音频 -->
        <div v-if="scene.audio_status === 'succeed' && scene.audio_url" style="margin-bottom:8px">
          <audio :src="scene.audio_url" controls style="width:100%"></audio>
        </div>

        <!-- 视频 -->
        <div v-if="scene.video_status === 'succeed' && scene.video_url" style="margin-bottom:8px">
          <video :src="scene.video_url" controls playsinline preload="metadata" style="max-width:100%;border-radius:4px"></video>
        </div>
        <div v-else-if="scene.video_status === 'failed'" style="font-size:12px;color:#dc2626;margin-bottom:4px">
          视频失败：{{ scene.video_error }}
        </div>

        <!-- 重试按钮 -->
        <button
          v-if="scene.image_status === 'failed' || scene.video_status === 'failed'"
          class="btn btn-outline"
          style="font-size:12px;padding:4px 10px"
          @click="handleRetryScene(scene.index)"
        >
          重试此场景
        </button>
      </div>
    </div>

    <!-- 会话信息 -->
    <div v-if="sessionId" style="text-align:center;color:#bbb;font-size:11px;margin-top:4px">
      session: {{ sessionId }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import {
  uploadVideo,
  startWorkflow,
  fetchRewriteStyles,
  rewriteText,
  confirmText,
  generateAudio,
  uploadAvatarImage,
  generateVideo,
  listSessions,
  getStatus,
  patchVideoResult,
  initStoryboard,
  generateAllScenes,
  getStoryboardStatus,
  retryScene,
  mergeStoryboard,
} from './api/workflow.js'

const STEPS = [
  { key: 'extract', label: '提取内容' },
  { key: 'rewrite', label: 'AI 改写' },
  { key: 'confirm', label: '确认文本' },
  { key: 'audio',   label: '形象与语音' },
  { key: 'video',   label: '生成视频' },
]

const STYLE_ICONS = { professional: '📋', casual: '💬', news: '📰' }

function isStepDone(i) {
  switch (i) {
    case 0:
      return hasExtractedText()
    case 1:
      return Boolean(normalizeText(editableText.value) && normalizeText(editableText.value) !== normalizeText(extractedText.value))
    case 2:
      return Boolean(normalizeText(finalText.value))
    case 3:
      return Boolean(audioUrl.value) && hasAvatarImage()
    case 4:
      return Boolean(videoUrl.value)
    default:
      return false
  }
}

function normalizeText(text) {
  return (text || '').trim()
}

function getDraftText() {
  return normalizeText(editableText.value) || normalizeText(finalText.value) || normalizeText(extractedText.value)
}

function hasExtractedText() {
  return Boolean(sessionId.value && normalizeText(extractedText.value))
}

function hasAvatarImage() {
  return Boolean(avatarImageFile.value || avatarImagePath.value)
}

function canVisitStep(i) {
  switch (i) {
    case 0:
      return true
    case 1:
      return hasExtractedText()
    case 2:
      return hasExtractedText()
    case 3:
      return Boolean(normalizeText(finalText.value))
    case 4:
      return Boolean(videoUrl.value || (normalizeText(finalText.value) && audioUrl.value && hasAvatarImage()))
    default:
      return false
  }
}

function getStepRequirement(i) {
  switch (i) {
    case 0:
      return '提取内容或重新开始'
    case 1:
      return '可直接查看原文并发起 AI 改写'
    case 2:
      return '可直接编辑待确认文本'
    case 3:
      return '上传数字人图片并生成语音'
    case 4:
      return '生成视频时会检查文本、图片和音频'
    default:
      return ''
  }
}

function getStepHint(i) {
  return `进入「${STEPS[i].label}」：${getStepRequirement(i)}`
}

function seedEditableText() {
  if (normalizeText(editableText.value)) return
  editableText.value = normalizeText(finalText.value) || normalizeText(extractedText.value)
}

function clearDerivedMedia() {
  audioUrl.value = ''
  videoUrl.value = ''
  videoStatus.value = ''
  videoError.value = ''
}

function resetAvatarImage() {
  if (avatarPreviewUrl.value && avatarPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(avatarPreviewUrl.value)
  }
  avatarImageFile.value = null
  avatarImagePath.value = ''
  avatarPreviewUrl.value = ''
}

function goToStep(i) {
  error.value = ''
  if (!canVisitStep(i)) {
    error.value = '请按顺序先完成前面的步骤。'
    return
  }
  if (i >= 2) seedEditableText()
  currentStep.value = i
}

// ── 状态 ────────────────────────────────────────────────
const currentStep  = ref(0)
const loading      = ref(false)
const error        = ref('')

const sourceMode   = ref('url')
const urlInput     = ref('')
const selectedFile = ref(null)
const isDragOver   = ref(false)

const sessionId    = ref('')
const extractedText = ref('')
const rewriteStyles = ref([])
const selectedStyle = ref('')
const editableText  = ref('')
const finalText     = ref('')
const audioUrl      = ref('')
const videoUrl      = ref('')
const videoStatus   = ref('')
const videoError    = ref('')
const videoProvider = ref('kling')   // 'kling' | 'baidu'
const patchTaskId   = ref('')
const patchLoading  = ref(false)
const avatarImageFile = ref(null)
const avatarImagePath = ref('')
const avatarPreviewUrl = ref('')
const taskSessions   = ref([])
const selectedSessionId = ref('')
const sessionLoading = ref(false)
const refreshLoading = ref(false)
let restoringSession = false

// ── 分镜状态 ─────────────────────────────────────────────
const storyboardMode    = ref(false)
const storyboardLoading = ref(false)
const storyboardScenes  = ref([])   // SceneInfo[]
const storyboardStatus  = ref('')   // init/processing/done/failed
const storyboardSuccessCount = ref(0)
const storyboardFailedCount  = ref(0)
const storyboardMergedUrl    = ref('')
const storyboardMerging      = ref(false)
let storyboardPollTimer = null

onMounted(async () => {
  try {
    rewriteStyles.value = await fetchRewriteStyles()
    if (rewriteStyles.value.length) selectedStyle.value = rewriteStyles.value[0].style_id
  } catch { /* 后端未启动时静默失败 */ }
  await refreshSessions()
})

onUnmounted(() => {
  stopStoryboardPolling()
})

watch(editableText, (nextText) => {
  const next = normalizeText(nextText)
  const confirmed = normalizeText(finalText.value)
  if (confirmed && next !== confirmed) {
    finalText.value = ''
    clearDerivedMedia()
  }
})


// ── 文件选择 ─────────────────────────────────────────────
function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}
function onDrop(e) {
  isDragOver.value = false
  const f = e.dataTransfer.files[0]
  if (f && f.type.startsWith('video/')) selectedFile.value = f
}

function onAvatarImageChange(e) {
  const file = e.target.files[0] || null
  if (avatarPreviewUrl.value && avatarPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(avatarPreviewUrl.value)
  }
  avatarImageFile.value = file
  avatarImagePath.value = ''
  avatarPreviewUrl.value = file ? URL.createObjectURL(file) : ''
  videoUrl.value = ''
  videoStatus.value = ''
  videoError.value = ''
}

function formatTaskOption(task) {
  const done = task.video_url ? ' / 已生成视频' : ''
  const preview = task.text_preview ? ` / ${task.text_preview}` : ''
  return `${task.session_id}${done}${preview}`
}

function stepIndexFromStatus(status) {
  switch (status.current_step) {
    case 'video_done':
    case 'video_pending':
    case 'video_failed':
      return 4
    case 'audio_done':
    case 'mode_selected':
    case 'confirmed':
      return 3
    case 'rewritten':
      return 2
    case 'extracted':
      return 1
    default:
      return 0
  }
}

async function refreshSessions() {
  try {
    taskSessions.value = await listSessions()
  } catch {
    taskSessions.value = []
  }
}

function applyWorkflowStatus(status) {
  restoringSession = true
  if (avatarPreviewUrl.value && avatarPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(avatarPreviewUrl.value)
  }
  sessionId.value = status.session_id
  selectedSessionId.value = status.session_id
  extractedText.value = status.extracted_text || ''
  editableText.value = status.final_text || status.rewritten_text || status.extracted_text || ''
  finalText.value = status.final_text || ''
  audioUrl.value = status.audio_url || ''
  videoUrl.value = status.video_url || ''
  videoStatus.value = status.video_status || (status.video_url ? 'succeed' : '')
  videoError.value = status.video_error || ''
  videoProvider.value = status.video_provider || 'kling'
  // 从超时错误信息里提取 task_id（可灵/百度），方便一键补录
  const tidMatch = (status.video_error || '').match(/task_id=([\w-]+)/)
  patchTaskId.value = tidMatch ? tidMatch[1] : ''
  avatarPreviewUrl.value = status.avatar_image_url || ''
  avatarImageFile.value = null
  avatarImagePath.value = status.avatar_image_url || (status.avatar_image_ready ? 'saved' : '')
  currentStep.value = stepIndexFromStatus(status)
  setTimeout(() => {
    restoringSession = false
  }, 0)
}

async function loadSelectedSession() {
  if (!selectedSessionId.value) return
  error.value = ''
  sessionLoading.value = true
  try {
    const status = await getStatus(selectedSessionId.value)
    applyWorkflowStatus(status)
  } catch (e) {
    error.value = e.message
  } finally {
    sessionLoading.value = false
  }
}


// ── 步骤处理函数 ─────────────────────────────────────────
async function handleExtract() {
  error.value = ''
  loading.value = true
  try {
    let source = ''
    if (sourceMode.value === 'url') {
      source = urlInput.value.trim()
    } else {
      const up = await uploadVideo(selectedFile.value)
      source = up.file_path
    }
    const res = await startWorkflow(source)
    sessionId.value    = res.session_id
    selectedSessionId.value = res.session_id
    extractedText.value = res.extracted_text
    editableText.value = res.extracted_text
    finalText.value = ''
    clearDerivedMedia()
    resetAvatarImage()
    currentStep.value  = 1
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function ensureTextSession() {
  if (!sessionId.value || !hasExtractedText()) {
    throw new Error('请先从第一步提取内容创建会话。')
  }
  return sessionId.value
}

async function handleRewrite() {
  error.value = ''
  if (!sessionId.value || !hasExtractedText()) {
    error.value = '请先提取内容，再执行 AI 改写。'
    return
  }
  loading.value = true
  try {
    const res = await rewriteText(sessionId.value, selectedStyle.value)
    editableText.value = res.rewritten_text
    finalText.value = ''
    clearDerivedMedia()
    currentStep.value  = 2
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleConfirm() {
  error.value = ''
  const draftText = getDraftText()
  if (!draftText) {
    error.value = '没有可确认的文本，请先提取内容或输入文本。'
    return
  }
  loading.value = true
  try {
    await ensureTextSession()
    const oldFinalText = normalizeText(finalText.value)
    const res = await confirmText(sessionId.value, draftText)
    if (oldFinalText && oldFinalText !== normalizeText(res.final_text)) {
      clearDerivedMedia()
    }
    editableText.value = res.final_text
    finalText.value   = res.final_text
    currentStep.value = 3
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function ensureConfirmedText() {
  seedEditableText()
  await ensureTextSession()
  const draftText = getDraftText()
  if (!draftText) {
    throw new Error('没有可用于继续流程的文本，请先提取内容或输入文本。')
  }
  if (normalizeText(finalText.value) === draftText) {
    return finalText.value
  }

  const res = await confirmText(sessionId.value, draftText)
  const nextFinalText = normalizeText(res.final_text)
  if (normalizeText(finalText.value) && normalizeText(finalText.value) !== nextFinalText) {
    clearDerivedMedia()
  }
  editableText.value = res.final_text
  finalText.value = res.final_text
  return res.final_text
}

async function ensureAvatarAudio() {
  await ensureConfirmedText()
  if (audioUrl.value) return audioUrl.value
  const res = await generateAudio(sessionId.value)
  audioUrl.value = res.audio_url
  await refreshSessions()
  return res.audio_url
}

async function ensureAvatarImageUploaded() {
  if (!sessionId.value) {
    throw new Error('请先提取内容创建会话，再继续后续步骤。')
  }
  if (avatarImagePath.value) return avatarImagePath.value
  if (!avatarImageFile.value) {
    throw new Error('请先上传一张数字人参考图。')
  }
  const res = await uploadAvatarImage(sessionId.value, avatarImageFile.value)
  if (avatarPreviewUrl.value && avatarPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(avatarPreviewUrl.value)
  }
  avatarImagePath.value = res.image_url || res.file_path
  avatarPreviewUrl.value = res.image_url || avatarPreviewUrl.value
  avatarImageFile.value = null
  await refreshSessions()
  return avatarImagePath.value
}

async function proceedToVideoStep() {
  error.value = ''
  if (!hasAvatarImage()) {
    error.value = '请先上传数字人参考图，再继续生成视频。'
    return
  }
  if (!audioUrl.value) {
    error.value = '请先生成语音，再继续生成视频。'
    return
  }
  loading.value = true
  try {
    await ensureAvatarImageUploaded()
    currentStep.value = 4
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleAudio() {
  error.value = ''
  loading.value = true
  try {
    await ensureAvatarAudio()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleVideo() {
  error.value = ''
  loading.value = true
  try {
    await ensureAvatarAudio()
    await ensureAvatarImageUploaded()
    const res = await generateVideo(sessionId.value, videoProvider.value)
    videoStatus.value = res.video_status || ''
    videoError.value = res.video_error || ''
    videoUrl.value = res.video_url || ''
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleRefreshVideoStatus() {
  if (!sessionId.value) return
  refreshLoading.value = true
  error.value = ''
  try {
    const status = await getStatus(sessionId.value)
    applyWorkflowStatus(status)
    if (status.video_url || status.video_status === 'succeed') {
      await refreshSessions()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    refreshLoading.value = false
  }
}

async function handleVideoPatch() {
  error.value = ''
  if (!patchTaskId.value.trim()) {
    error.value = '请填写百度云 task_id'
    return
  }
  patchLoading.value = true
  try {
    const res = await patchVideoResult(sessionId.value, { taskId: patchTaskId.value.trim(), provider: videoProvider.value })
    videoUrl.value  = res.video_url || ''
    videoStatus.value = 'succeed'
    videoError.value  = ''
    patchTaskId.value = ''
    await refreshSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    patchLoading.value = false
  }
}

// ── 分镜处理函数 ─────────────────────────────────────────
async function enterStoryboardMode() {
  error.value = ''
  storyboardLoading.value = true
  try {
    await ensureAvatarImageUploaded()
    const res = await initStoryboard(sessionId.value)
    storyboardScenes.value = res.scenes
    storyboardStatus.value = 'init'
    storyboardSuccessCount.value = 0
    storyboardFailedCount.value = 0
    storyboardMergedUrl.value = ''
    storyboardMode.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardLoading.value = false
  }
}

async function handleGenerateAll() {
  error.value = ''
  storyboardLoading.value = true
  try {
    await generateAllScenes(sessionId.value)
    startStoryboardPolling()
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardLoading.value = false
  }
}

function startStoryboardPolling() {
  stopStoryboardPolling()
  storyboardPollTimer = setInterval(async () => {
    try {
      const res = await getStoryboardStatus(sessionId.value)
      storyboardScenes.value = res.scenes
      storyboardStatus.value = res.status
      storyboardSuccessCount.value = res.succeed_count
      storyboardFailedCount.value = res.failed_count
      storyboardMergedUrl.value = res.merged_video_url || ''
      if (res.status !== 'processing') {
        stopStoryboardPolling()
      }
    } catch { /* ignore polling errors */ }
  }, 3000)
}

function stopStoryboardPolling() {
  if (storyboardPollTimer) {
    clearInterval(storyboardPollTimer)
    storyboardPollTimer = null
  }
}

async function handleRetryScene(sceneIndex) {
  error.value = ''
  try {
    await retryScene(sessionId.value, sceneIndex)
    startStoryboardPolling()
  } catch (e) {
    error.value = e.message
  }
}

async function handleMerge() {
  error.value = ''
  storyboardMerging.value = true
  try {
    const res = await mergeStoryboard(sessionId.value)
    storyboardMergedUrl.value = res.merged_video_url
  } catch (e) {
    error.value = e.message
  } finally {
    storyboardMerging.value = false
  }
}

function exitStoryboardMode() {
  stopStoryboardPolling()
  storyboardMode.value = false
}

function reset() {
  exitStoryboardMode()
  storyboardScenes.value = []
  storyboardStatus.value = ''
  storyboardSuccessCount.value = 0
  storyboardFailedCount.value = 0
  storyboardMergedUrl.value = ''
  storyboardMerging.value = false
  storyboardLoading.value = false
  currentStep.value    = 0
  sessionId.value      = ''
  selectedSessionId.value = ''
  urlInput.value       = ''
  selectedFile.value   = null
  extractedText.value  = ''
  editableText.value   = ''
  finalText.value      = ''
  audioUrl.value       = ''
  videoUrl.value       = ''
  videoStatus.value    = ''
  videoError.value     = ''
  videoProvider.value  = 'kling'
  patchTaskId.value    = ''
  resetAvatarImage()
  error.value          = ''
}
</script>
