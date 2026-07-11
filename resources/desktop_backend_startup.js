function normalizePath(value) {
  return String(value || "").replace(/\//g, "\\").toLowerCase();
}

function normalizePort(value) {
  const port = Number(value);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? port : null;
}

function buildPortCandidates(configuredPort, fallbacks) {
  const ports = [];
  for (const value of [configuredPort, ...(fallbacks || [])]) {
    const port = normalizePort(value);
    if (port && !ports.includes(port)) ports.push(port);
  }
  return ports;
}

function isCurrentBackendHealth(statusCode, body) {
  return (
    Number(statusCode) === 200 &&
    body &&
    body.status === "ok" &&
    body.aivo_desktop_backend === true &&
    body.dry_run === false
  );
}

function isOwnBackendProcessInfo(info, knownBackendRoots) {
  const name = String(info && info.name ? info.name : "").toLowerCase();
  const executablePath = normalizePath(info && info.executablePath);
  if (name !== "aivo_backend.exe") return false;
  if (!executablePath.endsWith("\\aivo_backend.exe")) return false;

  const normalizedRoots = (knownBackendRoots || []).map(normalizePath).filter(Boolean);
  if (normalizedRoots.some((root) => executablePath.startsWith(root.endsWith("\\") ? root : `${root}\\`))) {
    return true;
  }

  return (
    executablePath.includes("\\digital-human-agent-desktop\\resources\\backend\\") ||
    executablePath.includes("\\数字人智能体\\resources\\backend\\")
  );
}

function classifyPortBeforeStart({ owners, health, knownBackendRoots, port }) {
  if (isCurrentBackendHealth(health && health.statusCode, health && health.body)) {
    return { action: "reuse", killPids: [], reason: "current backend already healthy" };
  }

  const ownerList = Array.isArray(owners) ? owners : [];
  if (ownerList.length === 0) {
    return { action: "start", killPids: [], reason: "port is free" };
  }

  const killPids = ownerList
    .filter((owner) => isOwnBackendProcessInfo(owner, knownBackendRoots))
    .map((owner) => Number(owner.pid || owner.processId))
    .filter((pid) => Number.isInteger(pid) && pid > 0);

  if (killPids.length > 0) {
    return { action: "cleanup", killPids, reason: `stale backend on port ${port}` };
  }

  return { action: "skip", killPids: [], reason: `port ${port} is used by another process` };
}

module.exports = {
  buildPortCandidates,
  classifyPortBeforeStart,
  isCurrentBackendHealth,
  isOwnBackendProcessInfo
};
