// StoryForge FlowKit — MV3 service worker.
// Captures Google Labs Bearer token, opens a singleton WebSocket to the local
// StoryForge backend, and dispatches api_request / solve_captcha messages.

const DEFAULT_PORT = 7860;
const WS_PATH = "/api/ws/flowkit";
const TOKEN_HOSTS = ["aisandbox-pa.googleapis.com", "labs.google"];
// Outbound fetch hosts we will auto-attach the captured Bearer token to.
// Anything else: token withheld even if upstream WS asks. Mitigates a malicious
// localhost peer hijacking the singleton WS to exfiltrate the Google token.
const ALLOWED_FETCH_HOSTS = new Set([
  "aisandbox-pa.googleapis.com",
  "labs.google",
  "storage.googleapis.com",
]);
const KEEPALIVE_ALARM = "keepalive";
const RECONNECT_ALARM = "reconnect";
const REFRESH_ALARM = "token_refresh";
const TAB_SPAWN_COOLDOWN_MS = 60_000;

const state = {
  ws: null,
  status: "disconnected",
  port: DEFAULT_PORT,
  flowKey: null,
  callbackSecret: null,
  log: [],
  pendingCaptcha: new Map(),
  lastAuthTabSpawn: 0,
  bootstrapped: false,
};

function isAllowedFetchUrl(url) {
  try {
    const u = new URL(url);
    return ALLOWED_FETCH_HOSTS.has(u.hostname);
  } catch {
    return false;
  }
}

function pushLog(entry) {
  state.log.unshift({ ts: Date.now(), ...entry });
  if (state.log.length > 100) state.log.length = 100;
  chrome.runtime.sendMessage({ type: "STATE_UPDATE", state: snapshot() }).catch(() => {});
}

function snapshot() {
  return {
    status: state.status,
    port: state.port,
    flowKeyPresent: !!state.flowKey,
    log: state.log.slice(0, 50),
  };
}

function setStatus(next) {
  state.status = next;
  chrome.action.setBadgeText({ text: next === "connected" ? "" : next === "captcha" ? "!" : "x" });
  chrome.action.setBadgeBackgroundColor({ color: next === "captcha" ? "#d22" : "#888" });
  chrome.runtime.sendMessage({ type: "STATE_UPDATE", state: snapshot() }).catch(() => {});
}

async function loadConfig() {
  const data = await chrome.storage.local.get(["port", "flowKey"]);
  state.port = data.port || DEFAULT_PORT;
  state.flowKey = data.flowKey || null;
}

function connectWS() {
  if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;
  const url = `ws://127.0.0.1:${state.port}${WS_PATH}`;
  try {
    state.ws = new WebSocket(url);
  } catch (e) {
    pushLog({ kind: "error", msg: `WS construct failed: ${e.message}` });
    setStatus("disconnected");
    return;
  }
  state.ws.addEventListener("open", () => {
    setStatus("connected");
    pushLog({ kind: "ws", msg: "connected" });
    if (state.flowKey) sendWS({ type: "token_captured", token: state.flowKey });
  });
  state.ws.addEventListener("close", () => {
    setStatus("disconnected");
    pushLog({ kind: "ws", msg: "closed" });
  });
  state.ws.addEventListener("error", () => {
    pushLog({ kind: "ws", msg: "error" });
  });
  state.ws.addEventListener("message", onWSMessage);
}

function sendWS(payload) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(payload));
  }
}

async function onWSMessage(ev) {
  let msg;
  try { msg = JSON.parse(ev.data); } catch { return; }

  if (msg.type === "callback_secret") {
    state.callbackSecret = msg.secret;
    return;
  }
  if (msg.method === "api_request") return handleApiRequest(msg);
  if (msg.method === "solve_captcha") return handleSolveCaptcha(msg);
  if (msg.method === "media_urls_refresh") return handleMediaRefresh(msg);
  if (msg.type === "ping") return sendWS({ type: "pong" });
}

// Backend asks us to refresh expired GCS signed URLs (download_to_local hit 403/410).
// We can't re-sign a specific expired URL on demand — the injected.js fetch-hook only
// captures URLs as the Flow page fetches them, and those flow back via the passive
// "media_url_refreshed" channel. So this is acknowledged (not silently dropped) and
// best-effort: nudge the Flow tab so any in-page media re-fetch is observed.
function handleMediaRefresh(_msg) {
  pushLog({ kind: "media", msg: "refresh requested (best-effort; no on-demand re-sign)" });
}

async function handleApiRequest(msg) {
  const { id, params } = msg;
  const { url, method = "POST", headers = {}, body, captchaAction } = params || {};
  pushLog({ kind: "req", id, url, method });

  if (!isAllowedFetchUrl(url)) {
    sendWS({ id, status: 0, error: "url_not_allowed" });
    pushLog({ kind: "err", id, msg: "url host not allowlisted" });
    return;
  }

  try {
    const finalHeaders = {};
    for (const [k, v] of Object.entries(headers)) finalHeaders[k.toLowerCase()] = v;
    if (state.flowKey && !finalHeaders["authorization"]) {
      finalHeaders["authorization"] = `Bearer ${state.flowKey}`;
    }
    if (captchaAction) {
      const token = await requestCaptchaToken(captchaAction);
      if (token) finalHeaders["x-goog-recaptcha-token"] = token;
    }

    const res = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body && method !== "GET" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
      credentials: "omit",
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = text; }

    if (res.status === 401 || res.status === 403) {
      const now = Date.now();
      if (now - state.lastAuthTabSpawn > TAB_SPAWN_COOLDOWN_MS) {
        state.lastAuthTabSpawn = now;
        pushLog({ kind: "auth", msg: `token invalid (${res.status}) — opening Flow tab` });
        chrome.tabs.create({ url: "https://labs.google/fx/tools/flow", active: false });
      }
    }
    if (res.status === 429 || (data && data.captchaBlocked)) {
      setStatus("captcha");
      notifyCaptchaBlock();
    }

    sendWS({ id, status: res.status, data });
    pushLog({ kind: "res", id, status: res.status });
  } catch (e) {
    sendWS({ id, status: 0, error: e.message });
    pushLog({ kind: "err", id, msg: e.message });
  }
}

function requestCaptchaToken(action) {
  return new Promise((resolve) => {
    const reqId = `cap-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    state.pendingCaptcha.set(reqId, resolve);
    setTimeout(() => {
      if (state.pendingCaptcha.has(reqId)) {
        state.pendingCaptcha.delete(reqId);
        resolve(null);
      }
    }, 15000);
    chrome.tabs.query({
      url: [
        "https://labs.google/fx/tools/flow*",
        "https://labs.google/fx/*/tools/flow*",
      ],
    }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab) {
        state.pendingCaptcha.delete(reqId);
        resolve(null);
        return;
      }
      chrome.tabs.sendMessage(tab.id, { type: "GET_CAPTCHA", reqId, action }).catch(() => {
        state.pendingCaptcha.delete(reqId);
        resolve(null);
      });
    });
  });
}

async function handleSolveCaptcha(msg) {
  const token = await requestCaptchaToken(msg.params?.action || "image_generation");
  sendWS({ id: msg.id, status: token ? 200 : 0, data: { token } });
}

function notifyCaptchaBlock() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, { type: "SHOW_CAPTCHA_TOAST" }).catch(() => {});
    }
  });
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/128.png",
    title: "FlowKit blocked by CAPTCHA",
    message: "Open https://labs.google/fx/tools/flow and complete the challenge.",
  });
}

// --- Token capture ---------------------------------------------------------

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    const auth = (details.requestHeaders || []).find(h => h.name.toLowerCase() === "authorization");
    if (auth && auth.value && auth.value.startsWith("Bearer ")) {
      const token = auth.value.slice(7);
      if (token !== state.flowKey) {
        state.flowKey = token;
        chrome.storage.local.set({ flowKey: token });
        sendWS({ type: "token_captured", token });
        pushLog({ kind: "token", msg: "captured" });
      }
    }
  },
  { urls: ["https://aisandbox-pa.googleapis.com/*", "https://labs.google/*"] },
  ["requestHeaders", "extraHeaders"]
);

// --- Captcha bridge from content script ------------------------------------

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Origin gating: content scripts may only deliver captcha/media bridge messages.
  // POPUP_* must come from the extension popup (no sender.tab).
  const fromContent = !!sender.tab;
  if (msg.type === "CAPTCHA_RESULT" && fromContent && msg.reqId && state.pendingCaptcha.has(msg.reqId)) {
    const resolve = state.pendingCaptcha.get(msg.reqId);
    state.pendingCaptcha.delete(msg.reqId);
    resolve(msg.token || null);
    return;
  }
  if (msg.type === "TRPC_MEDIA_URL" && fromContent && msg.url) {
    sendWS({ type: "media_url_refreshed", url: msg.url, ttl: msg.ttl || 3600 });
    return;
  }
  if (msg.type === "POPUP_GET_STATE" && !fromContent) {
    sendResponse(snapshot());
    return true;
  }
  if (msg.type === "POPUP_SET_PORT" && !fromContent && Number.isInteger(msg.port)) {
    state.port = msg.port;
    chrome.storage.local.set({ port: msg.port });
    if (state.ws) try { state.ws.close(); } catch {}
    connectWS();
    sendResponse({ ok: true });
    return true;
  }
});

// --- Alarms ---------------------------------------------------------------

chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.4 });
chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 0.5 });
chrome.alarms.create(REFRESH_ALARM, { periodInMinutes: 45 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) sendWS({ type: "ping" });
  } else if (alarm.name === RECONNECT_ALARM) {
    if (!state.ws || state.ws.readyState === WebSocket.CLOSED) connectWS();
  } else if (alarm.name === REFRESH_ALARM) {
    chrome.tabs.create({ url: "https://labs.google/fx/tools/flow", active: false });
  }
});

// --- Bootstrap ------------------------------------------------------------

async function bootstrap() {
  if (state.bootstrapped) return;
  state.bootstrapped = true;
  await loadConfig();
  connectWS();
}

chrome.runtime.onStartup.addListener(bootstrap);
chrome.runtime.onInstalled.addListener(bootstrap);
bootstrap();
