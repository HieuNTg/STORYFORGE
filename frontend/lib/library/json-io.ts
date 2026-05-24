"use client";

/**
 * JSON import/export for Library stories.
 *
 * Security model:
 *   Primary XSS defense = React text rendering (auto-escapes). Story fields
 *   MUST NOT be rendered via `dangerouslySetInnerHTML`. The sanitizer below
 *   is *defense-in-depth* only: it strips obviously hostile substrings before
 *   they reach localStorage so accidental innerHTML usage cannot resurrect
 *   them. It is NOT a complete HTML sanitizer — if user-supplied HTML must
 *   ever be rendered, swap in DOMPurify and remove this function.
 */

import { storyExportSchema, type Story, type StoryExport } from "@/types/story";

const MAX_IMPORT_BYTES = 1_000_000;

const HTML_TAG_RE = /<\/?(script|iframe|object|embed|meta|link|style|svg|form|base|noscript|template)\b[^>]*>/gi;
const ON_ATTR_RE = /\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi;
const DANGER_URL_RE = /(javascript|data|vbscript)\s*:/gi;

function sanitize(value: string): string {
  return value
    .replace(HTML_TAG_RE, "")
    .replace(ON_ATTR_RE, "")
    .replace(DANGER_URL_RE, "");
}

function sanitizeStory(story: Story): Story {
  return {
    ...story,
    title: sanitize(story.title),
    description: sanitize(story.description),
    setting: sanitize(story.setting),
    tone: sanitize(story.tone),
    characters: story.characters.map((c) => ({
      ...c,
      name: sanitize(c.name),
      description: sanitize(c.description),
      backstory: sanitize(c.backstory),
      secret: sanitize(c.secret),
      conflict: sanitize(c.conflict),
    })),
    chapters: story.chapters.map((ch) => ({
      ...ch,
      title: sanitize(ch.title),
      content: sanitize(ch.content),
      summary: sanitize(ch.summary),
    })),
  };
}

function safeFilename(title: string): string {
  const slug = title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9-_ ]+/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .toLowerCase()
    .slice(0, 60);
  return slug || "story";
}

export function exportStory(story: Story): void {
  if (typeof window === "undefined") return;
  const payload: StoryExport = { version: 1, story };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${safeFilename(story.title)}.storyforge.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Defer revoke so Safari/older Webkit can finalize the download negotiation.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export type LibraryExportFormat = "docx" | "pdf" | "epub";

/**
 * Server-side export of a localStorage Story as DOCX/PDF/EPUB.
 *
 * Uploads the Story payload to `/api/export/library/{fmt}`, downloads the
 * returned binary, and triggers a Save-As in the browser. Throws on non-2xx.
 */
export async function exportStoryToFormat(
  story: Story,
  fmt: LibraryExportFormat,
): Promise<void> {
  if (typeof window === "undefined") return;
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const csrfMatch =
    typeof document !== "undefined"
      ? document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)
      : null;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrfMatch) headers["X-CSRF-Token"] = decodeURIComponent(csrfMatch[1]);

  const url = `${base.replace(/\/+$/, "")}/api/export/library/${fmt}`;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(story),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data?.error ?? data?.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail || `Export ${fmt.toUpperCase()} thất bại`);
  }

  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = `${safeFilename(story.title)}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
}

export async function importStory(file: File): Promise<Story> {
  if (file.size > MAX_IMPORT_BYTES) {
    throw new Error("file_too_large");
  }
  const text = await file.text();
  if (text.length > MAX_IMPORT_BYTES) {
    throw new Error("file_too_large");
  }
  let parsedJson: unknown;
  try {
    parsedJson = JSON.parse(text);
  } catch {
    throw new Error("invalid_json");
  }
  const parsed = storyExportSchema.parse(parsedJson);
  return sanitizeStory(parsed.story);
}

export const LIBRARY_IMPORT_MAX_BYTES = MAX_IMPORT_BYTES;
