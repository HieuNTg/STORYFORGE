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
