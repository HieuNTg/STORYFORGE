"use client";

/** Client-side story ID generator. NOT cryptographically secure — IDs are not auth tokens. */
export function genStoryId(): string {
  return `story-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
