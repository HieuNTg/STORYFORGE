/**
 * Tests for sse-sniffers.ts.
 *
 * Each test pins the canonical backend phrasing from the cited source line.
 * If the backend re-words a log message, the failing test name pinpoints
 * exactly which sniffer needs updating — so a frontend test failure becomes
 * the early-warning signal that the implicit SSE contract has changed.
 */

import { describe, it, expect } from 'vitest';
import {
  sniffChapterCompletion,
  sniffAgentTurn,
  sniffAgentsPhase,
  sniffDebateMarker,
  sniffReaderTurn,
  sniffStateRegistryTick,
  sniffParallelBatch,
} from '../sse-sniffers';

describe('sniffChapterCompletion', () => {
  it('parses ✅ prefixed Vietnamese chapter line', () => {
    expect(sniffChapterCompletion('✅ Chương 3: Đại Đạo Triều Thiên')).toBe(
      'Ch. 3 — Đại Đạo Triều Thiên',
    );
  });

  it('parses Vietnamese chapter line without check mark', () => {
    expect(sniffChapterCompletion('Chương 12: Kết thúc')).toBe('Ch. 12 — Kết thúc');
  });

  it('parses English fallback chapter line', () => {
    expect(sniffChapterCompletion('Chapter 1: Beginning')).toBe('Ch. 1 — Beginning');
  });

  it('collapses internal whitespace in the title', () => {
    expect(sniffChapterCompletion('Chương 5:    Title   With    Spaces  ')).toBe(
      'Ch. 5 — Title With Spaces',
    );
  });

  it('returns null for layer markers', () => {
    expect(sniffChapterCompletion('Layer 2 starting')).toBeNull();
  });

  it('returns null for arbitrary log lines', () => {
    expect(sniffChapterCompletion('arbitrary log')).toBeNull();
  });

  it('returns null for [Agent …] lines', () => {
    expect(sniffChapterCompletion('[Agent 1/6] Sage: argue')).toBeNull();
  });
});

describe('sniffAgentTurn', () => {
  it('parses canonical simulator.py:633 form', () => {
    expect(sniffAgentTurn('[Agent 3/6] Sage: argue')).toEqual({
      idx: 3,
      total: 6,
      name: 'Sage',
      action: 'argue',
    });
  });

  it('parses skip action', () => {
    expect(sniffAgentTurn('[Agent 1/4] Cynic: skip')).toEqual({
      idx: 1,
      total: 4,
      name: 'Cynic',
      action: 'skip',
    });
  });

  it('parses multi-word action and trimmed name', () => {
    expect(sniffAgentTurn('[Agent 2/3]  Devil  Advocate :  raise objection')).toEqual({
      idx: 2,
      total: 3,
      name: 'Devil  Advocate',
      action: 'raise objection',
    });
  });

  it('returns null when prefix is wrong', () => {
    expect(sniffAgentTurn('[AGENTS] Layer 1 được duyệt!')).toBeNull();
    expect(sniffAgentTurn('Agent 3/6 Sage: argue')).toBeNull();
    expect(sniffAgentTurn('[Agent] Sage: argue')).toBeNull();
  });
});

describe('sniffAgentsPhase', () => {
  it('parses approved-layer marker (agent_registry.py:237)', () => {
    expect(sniffAgentsPhase('[AGENTS] Layer 1 được duyệt!')).toEqual({
      phase: 'approved',
      layer: 1,
    });
    expect(sniffAgentsPhase('[AGENTS] Layer 2 được duyệt!')).toEqual({
      phase: 'approved',
      layer: 2,
    });
  });

  it('parses revision marker (agent_registry.py:242)', () => {
    expect(sniffAgentsPhase('[AGENTS] Cần chỉnh sửa, vòng tiếp theo...')).toEqual({
      phase: 'revision',
    });
  });

  it('returns null for unrelated [AGENTS] prose', () => {
    expect(sniffAgentsPhase('[AGENTS] doing something else')).toBeNull();
  });

  it('returns null for non-[AGENTS] lines', () => {
    expect(sniffAgentsPhase('Chương 1: Khởi đầu')).toBeNull();
  });
});

describe('sniffDebateMarker', () => {
  it('returns the trailing message for [DEBATE] lines', () => {
    expect(sniffDebateMarker('[DEBATE] Round 2 token budget would be exceeded'))
      .toBe('Round 2 token budget would be exceeded');
  });

  it('returns null for non-[DEBATE] lines', () => {
    expect(sniffDebateMarker('[AGENTS] anything')).toBeNull();
    expect(sniffDebateMarker('arbitrary')).toBeNull();
  });
});

describe('sniffReaderTurn', () => {
  it('parses reader_simulator.py:94 form', () => {
    expect(sniffReaderTurn('[Reader] Simulating chapter 4...')).toEqual({ chapter: 4 });
  });

  it('returns null for non-Reader prefixes', () => {
    expect(sniffReaderTurn('[Agent 1/6] Sage: argue')).toBeNull();
  });
});

describe('sniffStateRegistryTick', () => {
  it('parses character_state_registry.py:135 form', () => {
    expect(sniffStateRegistryTick('[StateRegistry] Extracted states for ch7'))
      .toEqual({ chapter: 7 });
  });

  it('returns null for setting-graph lookalike', () => {
    expect(sniffStateRegistryTick('[SettingGraph] Processed ch7')).toBeNull();
  });
});

describe('sniffParallelBatch', () => {
  it('parses batch_generator.py:1292 form', () => {
    expect(sniffParallelBatch('[ASYNC] Đang viết 5 chương song song...'))
      .toEqual({ batchSize: 5 });
  });

  it('returns null for non-ASYNC prefixes', () => {
    expect(sniffParallelBatch('[Reader] Simulating chapter 1...')).toBeNull();
  });
});
