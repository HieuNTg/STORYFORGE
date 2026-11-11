import { apiFetch } from "@/lib/api/client";

export interface SessionState {
  required: boolean;
  valid: boolean;
}

export function getSession(): Promise<SessionState> {
  return apiFetch<SessionState>("/api/session");
}

/** Exchange the access token for the session cookie. Throws ApiError(401) if wrong. */
export async function openSession(token: string): Promise<void> {
  await apiFetch<void>("/api/session", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}
