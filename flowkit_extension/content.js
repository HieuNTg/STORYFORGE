// content.js — ISOLATED world. Bridges page <-> background, renders Toast UI.

(function injectMainWorldScript() {
  const s = document.createElement("script");
  s.src = chrome.runtime.getURL("injected.js");
  s.async = false;
  (document.head || document.documentElement).appendChild(s);
  s.onload = () => s.remove();
})();

// page -> content -> background
window.addEventListener("message", (ev) => {
  if (ev.source !== window || !ev.data || ev.data.__sf !== "flowkit") return;
  const { type, reqId, token, url, ttl } = ev.data;
  if (type === "CAPTCHA_RESULT") {
    chrome.runtime.sendMessage({ type: "CAPTCHA_RESULT", reqId, token }).catch(() => {});
  } else if (type === "TRPC_MEDIA_URL") {
    chrome.runtime.sendMessage({ type: "TRPC_MEDIA_URL", url, ttl }).catch(() => {});
  }
});

// background -> content
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "GET_CAPTCHA") {
    window.postMessage({ __sf: "flowkit", type: "GET_CAPTCHA", reqId: msg.reqId, action: msg.action }, location.origin);
  } else if (msg.type === "SHOW_CAPTCHA_TOAST") {
    showToast("FlowKit blocked by CAPTCHA. Complete the challenge in this tab.");
  }
});

function showToast(text) {
  let el = document.getElementById("__sf_flowkit_toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "__sf_flowkit_toast";
    el.style.cssText = [
      "position:fixed", "top:16px", "right:16px",
      "z-index:2147483647",
      "background:#d22", "color:#fff",
      "padding:12px 16px", "border-radius:6px",
      "font-family:system-ui,sans-serif", "font-size:13px",
      "box-shadow:0 4px 12px rgba(0,0,0,.3)",
      "max-width:320px",
      "animation:__sf_blink 1s ease-in-out infinite",
    ].join(";");
    const style = document.createElement("style");
    style.textContent = "@keyframes __sf_blink { 50% { opacity: 0.6; } }";
    document.head.appendChild(style);
    document.body.appendChild(el);
  }
  el.textContent = text;
  clearTimeout(el.__sfTimer);
  el.__sfTimer = setTimeout(() => { el && el.remove(); }, 30000);
}
