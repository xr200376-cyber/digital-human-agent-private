/**
 * 封装所有后端 workflow API 调用。
 * 所有请求通过 vite proxy 转发到 http://127.0.0.1:8000
 */

const BASE = ''  // vite proxy 已转发，无需前缀

async function request(method, path, body) {
  const opts = {
    method,
    headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

/** 步骤 0：上传视频文件，返回服务器路径 */
export async function uploadVideo(file) {
  const form = new FormData()
  form.append('file', file)
  return request('POST', '/workflow/upload', form)
}

/** 步骤 1：提交 URL 或文件路径，提取文本 */
export async function startWorkflow(source = '', rawText = '') {
  return request('POST', '/workflow/start', { source, raw_text: rawText })
}

/** 查询所有可用改写风格 */
export async function fetchRewriteStyles() {
  return request('GET', '/rewrite-styles')
}

/** 查询最近的工作流任务 */
export async function listSessions(limit = 50) {
  return request('GET', `/workflow/sessions?limit=${limit}`)
}

/** 步骤 2：改写文本 */
export async function rewriteText(sessionId, styleId) {
  return request('POST', `/workflow/${sessionId}/rewrite`, { style_id: styleId })
}

/** 步骤 3：确认文本 */
export async function confirmText(sessionId, finalText) {
  return request('POST', `/workflow/${sessionId}/confirm`, { final_text: finalText })
}

/** 步骤 4a：生成 TTS 音频 */
export async function generateAudio(sessionId) {
  return request('POST', `/workflow/${sessionId}/audio`)
}

/** 步骤 4b：上传数字人参考图 */
export async function uploadAvatarImage(sessionId, file) {
  const form = new FormData()
  form.append('file', file)
  return request('POST', `/workflow/${sessionId}/avatar-image`, form)
}

/** 步骤 5：异步提交数字人口播视频任务，provider: 'kling' | 'baidu' */
export async function generateVideo(sessionId, provider = 'kling') {
  return request('POST', `/workflow/${sessionId}/video`, { mode: 'avatar', provider })
}

/** 查询工作流状态 */
export async function getStatus(sessionId) {
  return request('GET', `/workflow/${sessionId}/status`)
}

/** 手动补录视频结果：传 task_id 让后端查询，或直接传 video_url */
export async function patchVideoResult(sessionId, { taskId = '', videoUrl = '', provider = '' } = {}) {
  return request('POST', `/workflow/${sessionId}/video-patch`, {
    task_id: taskId,
    video_url: videoUrl,
    provider,
  })
}

/** 分镜：拆分文案，创建分镜场景列表 */
export async function initStoryboard(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/init`)
}

/** 分镜：启动所有场景的后台生成任务 */
export async function generateAllScenes(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/generate-all`)
}

/** 分镜：查询整体状态和每个场景状态 */
export async function getStoryboardStatus(sessionId) {
  return request('GET', `/workflow/${sessionId}/storyboard/status`)
}

/** 分镜：重试指定场景（scene_index 从 0 开始） */
export async function retryScene(sessionId, sceneIndex) {
  return request('POST', `/workflow/${sessionId}/storyboard/scene/${sceneIndex}/retry`)
}

/** 分镜：合并所有场景视频，返回 merged_video_url */
export async function mergeStoryboard(sessionId) {
  return request('POST', `/workflow/${sessionId}/storyboard/merge`)
}
