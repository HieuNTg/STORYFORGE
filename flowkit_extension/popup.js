const statusEl = document.getElementById("status");
const tokenEl = document.getElementById("token-state");
const logEl = document.getElementById("log");
const portInput = document.getElementById("port");
const saveBtn = document.getElementById("save-port");

function render(state) {
  if (!state) return;
  statusEl.textContent = state.status;
  statusEl.className = `badge ${state.status}`;
  tokenEl.textContent = state.flowKeyPresent ? "(token captured)" : "(no token)";
  if (document.activeElement !== portInput) portInput.value = state.port;
  logEl.replaceChildren();
  (state.log || []).forEach((e) => {
    const div = document.createElement("div");
    div.className = "log-entry";
    const ts = document.createElement("span");
    ts.className = "ts";
    ts.textContent = new Date(e.ts).toLocaleTimeString();
    const kind = document.createElement("span");
    kind.textContent = ` [${e.kind}] `;
    const detail = document.createElement("span");
    detail.textContent = e.url ? `${e.method || ""} ${e.url}` : e.msg || JSON.stringify(e);
    div.append(ts, kind, detail);
    logEl.appendChild(div);
  });
}

chrome.runtime.sendMessage({ type: "POPUP_GET_STATE" }, render);
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "STATE_UPDATE") render(msg.state);
});

saveBtn.addEventListener("click", () => {
  const port = parseInt(portInput.value, 10);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    alert("Port must be 1024-65535");
    return;
  }
  chrome.runtime.sendMessage({ type: "POPUP_SET_PORT", port }, () => {
    chrome.runtime.sendMessage({ type: "POPUP_GET_STATE" }, render);
  });
});
