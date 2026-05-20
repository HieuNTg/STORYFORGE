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
