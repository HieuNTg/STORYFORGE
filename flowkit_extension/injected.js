// injected.js — runs in MAIN world (page context). Hooks grecaptcha + fetch.

(function () {
  const SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"; // Google Labs Flow reCAPTCHA Enterprise v3

  function post(type, payload) {
    window.postMessage({ __sf: "flowkit", type, ...payload }, location.origin);
  }

  // Listen for captcha requests from content script.
  window.addEventListener("message", async (ev) => {
    if (ev.source !== window || !ev.data || ev.data.__sf !== "flowkit") return;
    if (ev.data.type !== "GET_CAPTCHA") return;
    const { reqId, action } = ev.data;
    try {
      const g = window.grecaptcha && window.grecaptcha.enterprise;
      if (!g || typeof g.execute !== "function") {
        post("CAPTCHA_RESULT", { reqId, token: null });
        return;
      }
      const token = await g.execute(SITE_KEY, { action: action || "image_generation" });
      post("CAPTCHA_RESULT", { reqId, token });
    } catch {
      post("CAPTCHA_RESULT", { reqId, token: null });
    }
  });

  // Monkey-patch fetch to sniff TRPC media URL refreshes (GCS signed URLs).
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
      if (url && url.includes("/fx/api/trpc/") && url.includes("media")) {
        const clone = res.clone();
        clone.json().then((json) => {
          const urls = extractGcsUrls(json);
          urls.forEach((u) => post("TRPC_MEDIA_URL", { url: u, ttl: 3600 }));
        }).catch(() => {});
      }
    } catch {}
    return res;
  };

  function extractGcsUrls(obj, acc = []) {
    if (!obj) return acc;
    if (typeof obj === "string") {
      try {
        const u = new URL(obj);
        if (u.hostname === "storage.googleapis.com") acc.push(obj);
      } catch {}
      return acc;
    }
    if (Array.isArray(obj)) { obj.forEach((v) => extractGcsUrls(v, acc)); return acc; }
    if (typeof obj === "object") { Object.values(obj).forEach((v) => extractGcsUrls(v, acc)); }
    return acc;
  }
})();
