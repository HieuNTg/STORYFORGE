/**
 * Frontend mirror of `models/schemas.py` ForgeResponse + Library story shape.
 *
 * Source-of-truth is Python (Pydantic). Sync by hand; e2e test catches drift.
 */
import { z } from "zod";

export const forgeRoleSchema = z.enum([
  "protagonist",
  "antagonist",
  "rival",
  "supporting",
]);
export type ForgeRole = z.infer<typeof forgeRoleSchema>;

export const traitKeySchema = z.enum([
  "strength",
  "wisdom",
  "agility",
  "scheme",
]);
export type TraitKey = z.infer<typeof traitKeySchema>;

export const traitsSchema = z.object({
  strength: z.number().int().min(0).max(100),
  wisdom: z.number().int().min(0).max(100),
  agility: z.number().int().min(0).max(100),
  scheme: z.number().int().min(0).max(100),
});
export type Traits = z.infer<typeof traitsSchema>;

export const forgeCharacterSchema = z.object({
  name: z.string().min(1),
  role: forgeRoleSchema,
  traits: traitsSchema,
  description: z.string(),
  backstory: z.string(),
  secret: z.string(),
  conflict: z.string(),
});
export type ForgeCharacter = z.infer<typeof forgeCharacterSchema>;

export const forgeChoiceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  actionPrompt: z.string().min(1),
});
export type ForgeChoice = z.infer<typeof forgeChoiceSchema>;

export const forgeChapterSchema = z.object({
  title: z.string().min(1),
  content: z.string().min(1),
  summary: z.string(),
  choices: z.array(forgeChoiceSchema).length(2),
});
export type ForgeChapter = z.infer<typeof forgeChapterSchema>;

export const forgeResponseSchema = z.object({
  title: z.string().min(1),
  genre: z.string(),
  setting: z.string(),
  tone: z.string(),
  description: z.string(),
  characters: z.array(forgeCharacterSchema).length(2),
  firstChapter: forgeChapterSchema,
});
export type ForgeResponse = z.infer<typeof forgeResponseSchema>;

export const forgeRequestSchema = z.object({
  sentenceIdea: z.string().min(10).max(500),
});
export type ForgeRequest = z.infer<typeof forgeRequestSchema>;

export const characterGenerateRequestSchema = z.object({
  name: z.string().min(1).max(80),
  role: forgeRoleSchema,
  genre: z.string().min(1).max(80),
  extraContext: z.string().max(2000).optional(),
});
export type CharacterGenerateRequest = z.infer<typeof characterGenerateRequestSchema>;

// ---------------------------------------------------------------------------
// Library Story (client-side persisted shape)
// ---------------------------------------------------------------------------

export const storyChapterSchema = z.object({
  id: z.string(),
  title: z.string(),
  content: z.string(),
  summary: z.string().default(""),
  /** "ĐK" = Đặc khu (forge ch1), "Ch" = standard chapter. */
  badge: z.enum(["ĐK", "Ch"]).default("Ch"),
  status: z.enum(["draft", "ready", "enhanced"]).default("ready"),
  createdAt: z.string(),
});
export type StoryChapter = z.infer<typeof storyChapterSchema>;

export const storySchema = z.object({
  id: z.string(),
  title: z.string(),
  genre: z.string(),
  setting: z.string().default(""),
  tone: z.string().default(""),
  description: z.string().default(""),
  coverUrl: z.string().nullable().default(null),
  characters: z.array(forgeCharacterSchema).default([]),
  chapters: z.array(storyChapterSchema).default([]),
  /** When set, the unconsumed pair of choices from the latest forge call. */
  pendingChoices: z.array(forgeChoiceSchema).nullable().default(null),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type Story = z.infer<typeof storySchema>;

// ---------------------------------------------------------------------------
// Simulation Transcript (Phase 3) — mirrors models/schemas.py
// ---------------------------------------------------------------------------

export const dramaLevelSchema = z.enum(["low", "medium", "high", "climax"]);
export type DramaLevel = z.infer<typeof dramaLevelSchema>;

export const transcriptTurnSchema = z.object({
  id: z.string().min(1).max(64),
  senderId: z.string().min(1).max(80),
  senderName: z.string().min(1).max(80),
  emotion: z.string().max(80).default(""),
  actionDetails: z.string().max(2000).default(""),
  speech: z.string().max(2000).default(""),
});
export type TranscriptTurn = z.infer<typeof transcriptTurnSchema>;

export const simulationTranscriptSchema = z.object({
  logs: z.array(transcriptTurnSchema).default([]),
  outcomeSummary: z.string().max(4000).default(""),
});
export type SimulationTranscript = z.infer<typeof simulationTranscriptSchema>;

export const simulationContinueRequestSchema = z.object({
  characters: z.array(z.record(z.string(), z.unknown())).min(1).max(10),
  historyLogs: z.array(transcriptTurnSchema).max(6).default([]),
  topic: z.string().min(1).max(2000),
  dramaLevel: dramaLevelSchema.default("high"),
});
export type SimulationContinueRequest = z.infer<typeof simulationContinueRequestSchema>;

export const storyExportSchema = z.object({
  version: z.literal(1),
  story: storySchema,
});
export type StoryExport = z.infer<typeof storyExportSchema>;
