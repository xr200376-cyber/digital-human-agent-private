const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aivoDesktop", {
  getSettings: () => ipcRenderer.invoke("desktop:get-settings"),
  saveSettings: (settings) => ipcRenderer.invoke("desktop:save-settings", settings),
  startBackend: () => ipcRenderer.invoke("desktop:start-backend"),
  restartBackend: () => ipcRenderer.invoke("desktop:restart-backend"),
  stopBackend: () => ipcRenderer.invoke("desktop:stop-backend"),
  getLogs: () => ipcRenderer.invoke("desktop:get-logs"),
  validateSettings: (settings) => ipcRenderer.invoke("desktop:validate-settings", settings),
  getAlignmentReport: (settings) => ipcRenderer.invoke("desktop:get-alignment-report", settings),
  getSimpleSettings: () => ipcRenderer.invoke("desktop:simple-settings"),
  applySettingsPreset: (request) => ipcRenderer.invoke("desktop:apply-settings-preset", request),
  autoDetectSettings: () => ipcRenderer.invoke("desktop:autodetect-settings"),
  validateSimpleSettings: (settings) => ipcRenderer.invoke("desktop:validate-simple-settings", settings),
  copyEnv: (settings) => ipcRenderer.invoke("desktop:copy-env", settings),
  estimateCloudCost: (payload) => ipcRenderer.invoke("desktop:cloud-cost-estimate", payload),
  getSimpleAlignmentReport: () => ipcRenderer.invoke("desktop:simple-alignment-report"),
  openStudio: () => ipcRenderer.invoke("desktop:open-studio"),
  openExternalUrl: (url) => ipcRenderer.invoke("desktop:open-external-url", url)
});
