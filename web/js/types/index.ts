/**
 * types/index.ts — Shared domain type definitions for StoryForge frontend.
 *
 * Import from other TS/JS files via:
 *   import type { Story, Chapter } from '@/types'
 */

// ---------------------------------------------------------------------------
// Enumerations
// ---------------------------------------------------------------------------

export type ExportFormat = 'pdf' | 'epub' | 'html' | 'zip'

export type Genre =
  | 'fantasy'
  | 'sci-fi'
  | 'romance'
  | 'mystery'
  | 'thriller'
  | 'horror'
  | 'historical'
  | 'literary'
  | 'adventure'
  | 'other'

export type Language =
  | 'en'
  | 'es'
  | 'fr'
  | 'de'
  | 'it'
  | 'pt'
  | 'zh'
  | 'ja'
  | 'ko'
  | string // allow arbitrary BCP-47 language tags

export type PipelineStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'paused'
  | 'done'
  | 'error'
  | 'interrupted'

// ---------------------------------------------------------------------------
// Core domain models
// ---------------------------------------------------------------------------

export interface Character {
  id: string
  name: string
  role: 'protagonist' | 'antagonist' | 'supporting' | 'minor'
  description: string
  traits: string[]
  arc?: string
}

export interface Chapter {
  id: string
  storyId: string
  index: number
  title: string
  content: string
  wordCount: number
  createdAt: string   // ISO 8601
  updatedAt: string
}

export interface Story {
  id: string
  title: string
  genre: Genre
  language: Language
  synopsis: string
  chapters: Chapter[]
  characters: Character[]
  wordCount: number
  status: PipelineStatus
  createdAt: string   // ISO 8601
  updatedAt: string
  coverImageUrl?: string
  tags: string[]
}

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

export interface UserProfile {
  id: string
  email: string
  displayName: string
  avatarUrl?: string
  plan: 'free' | 'pro' | 'enterprise'
  storiesCreated: number
  createdAt: string
}

// ---------------------------------------------------------------------------
// Pipeline / generation config
// ---------------------------------------------------------------------------

export interface PipelineConfig {
  genre: Genre
  language: Language
  targetWordCount: number
  chapterCount: number
  temperature?: number      // 0–2, default 0.9
  model?: string            // e.g. "gpt-4o"
  outline?: string
  characters?: Pick<Character, 'name' | 'role' | 'description'>[]
  streamBufferMs?: number   // batching window for streamBuffered(), default 500
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

/** Generic API envelope */
export interface ApiResponse<T> {
  data: T;
  error?: string;
}

/** GET /api/dashboard/summary */
export interface DashboardSummary {
  total_stories: number;
  total_generations: number;
  avg_quality_score: number;
  recent_stories: Story[];
}

/** POST /api/pipeline/run request */
export interface PipelineRunRequest {
  idea: string;
  genre?: string;
  num_chapters?: number;
  num_characters?: number;
  words_per_chapter?: number;
  num_sim_rounds?: number;
  language?: string;
  enable_quality_gate?: boolean;
  enable_smart_revision?: boolean;
  lite_mode?: boolean;
}

/** Shape of a completed pipeline result */
export interface PipelineOutput {
  story_id: string;
  title: string;
  chapters: Chapter[];
  characters: Character[];
  [key: string]: unknown;
}

/** SSE event from /api/pipeline/run */
export interface PipelineStreamEvent {
  type: 'progress' | 'log' | 'result' | 'error';
  data: string | number | PipelineOutput;
}

/** GET /api/config */
export interface StoryForgeConfig {
  provider: string;
  model: string;
  api_key_set: boolean;
  language: string;
  image_provider?: string;
  cheap_model?: string;
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
}

/** POST /api/export/{format} */
export interface ExportRequest {
  story_id: string;
  format: 'pdf' | 'epub' | 'html' | 'txt';
}

export interface ExportResponse {
  url: string;
  filename: string;
  format: string;
}
