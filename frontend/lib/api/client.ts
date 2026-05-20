/**
 * Typed fetch wrapper for the StoryForge FastAPI backend.
 * - Reads `csrf_token` cookie, injects `X-CSRF-Token` header.
 * - Normalizes error responses to `{ error: { code, message } }`.
 * - Throws `ApiError` on non-2xx.
 */

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

function joinUrl(base: string, path: string): string {
  if (!base) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

async function normalizeError(res: Response): Promise<ApiError> {
  let bodyText = "";
  try {
    bodyText = await res.text();
  } catch {
    /* empty */
  }
  let parsed: Partial<ApiErrorEnvelope> | null = null;
  try {
    parsed = bodyText ? (JSON.parse(bodyText) as Partial<ApiErrorEnvelope>) : null;
  } catch {
    parsed = null;
  }
  const code = parsed?.error?.code ?? `http_${res.status}`;
  const message = parsed?.error?.message ?? res.statusText ?? "Request failed";
  return new ApiError(res.status, code, message, parsed?.error?.details);
}

export async function apiFetch<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const url = joinUrl(base, path);

  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init?.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const csrf = getCookie("csrf_token");
  if (csrf) headers.set("X-CSRF-Token", csrf);

  const res = await fetch(url, { ...init, headers, credentials: "include" });
  if (!res.ok) throw await normalizeError(res);

  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}
