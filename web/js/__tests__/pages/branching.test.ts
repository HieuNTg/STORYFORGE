/**
 * pages/branching.test.ts
 *
 * Unit tests for forgeBranchTreeMount Alpine.data factory and treeApiToBranchNodes.
 *
 * Covers:
 *   - forgeBranchTreeMount: default state
 *   - setSession: no-op when same session, resets on new session
 *   - refresh: no-op when _sessionId null
 *   - refresh: happy path — fetch called, nodes populated, loaded = true
 *   - refresh: HTTP error path — error set, loaded = false
 *   - refresh: network error path — error set, loaded = false
 *   - treeApiToBranchNodes: empty / missing nodes, normal conversion, label truncation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { forgeBranchTreeMount, treeApiToBranchNodes } from '../../pages/branching';

// ── treeApiToBranchNodes ──────────────────────────────────────────────────────

describe('treeApiToBranchNodes', () => {
  it('returns [] for null input', () => {
    // @ts-expect-error deliberate bad input
    expect(treeApiToBranchNodes(null)).toEqual([]);
  });

  it('returns [] when nodes is missing', () => {
    // @ts-expect-error deliberate bad input
    expect(treeApiToBranchNodes({ session_id: 'x', root: 'r', current: 'r' })).toEqual([]);
  });

  it('converts a single node', () => {
    const data = {
      session_id: 's1',
      root: 'n1',
      current: 'n1',
      nodes: {
        n1: { id: 'n1', text: 'Hello world', choices: [], parent: null, child_ids: [], depth: 0 },
      },
    };
    const result = treeApiToBranchNodes(data);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ id: 'n1', label: 'Hello world', parentId: null, depth: 0 });
  });

  it('truncates label at 40 chars and appends ellipsis', () => {
    const longText = 'A'.repeat(50);
    const data = {
      session_id: 's1',
      root: 'n1',
      current: 'n1',
      nodes: {
        n1: { id: 'n1', text: longText, choices: [], parent: null, child_ids: [], depth: 0 },
      },
    };
    const result = treeApiToBranchNodes(data);
    expect(result[0].label).toBe('A'.repeat(40) + '…');
  });

  it('preserves 40-char text without ellipsis', () => {
    const text40 = 'B'.repeat(40);
    const data = {
      session_id: 's1',
      root: 'n1',
      current: 'n1',
      nodes: {
        n1: { id: 'n1', text: text40, choices: [], parent: null, child_ids: [], depth: 0 },
      },
    };
    const result = treeApiToBranchNodes(data);
    expect(result[0].label).toBe(text40);
  });

  it('maps parentId and depth correctly for a child node', () => {
    const data = {
      session_id: 's1',
      root: 'root',
      current: 'child',
      nodes: {
        root: { id: 'root', text: 'Root', choices: ['go'], parent: null, child_ids: ['child'], depth: 0 },
        child: { id: 'child', text: 'Child', choices: [], parent: 'root', child_ids: [], depth: 1 },
      },
    };
    const result = treeApiToBranchNodes(data);
    const child = result.find((n) => n.id === 'child');
    expect(child).toBeDefined();
    expect(child!.parentId).toBe('root');
    expect(child!.depth).toBe(1);
  });
});

// ── forgeBranchTreeMount ──────────────────────────────────────────────────────

describe('forgeBranchTreeMount', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns correct default state', () => {
    const m = forgeBranchTreeMount();
    expect(m._sessionId).toBeNull();
    expect(m.nodes).toEqual([]);
    expect(m.currentNode).toBeNull();
    expect(m.loading).toBe(false);
    expect(m.error).toBeNull();
    expect(m.loaded).toBe(false);
  });

  it('setSession updates _sessionId and resets state', () => {
    const m = forgeBranchTreeMount();
    // Manually set some state first
    m.loaded = true;
    m.nodes = [{ id: 'x', label: 'X', parentId: null, depth: 0 }];
    m.setSession('abc');
    expect(m._sessionId).toBe('abc');
    expect(m.nodes).toEqual([]);
    expect(m.loaded).toBe(false);
    expect(m.error).toBeNull();
  });

  it('setSession is a no-op when called with same session id', () => {
    const m = forgeBranchTreeMount();
    m._sessionId = 'abc';
    m.loaded = true;
    m.nodes = [{ id: 'x', label: 'X', parentId: null, depth: 0 }];
    m.setSession('abc');
    // state unchanged
    expect(m.loaded).toBe(true);
    expect(m.nodes).toHaveLength(1);
  });

  it('refresh is a no-op when _sessionId is null', async () => {
    const m = forgeBranchTreeMount();
    await m.refresh();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(m.loading).toBe(false);
  });

  it('refresh happy path: sets nodes, currentNode, loaded = true', async () => {
    const apiResponse = {
      session_id: 'sess1',
      root: 'n1',
      current: 'n2',
      nodes: {
        n1: { id: 'n1', text: 'Root', choices: ['go'], parent: null, child_ids: ['n2'], depth: 0 },
        n2: { id: 'n2', text: 'Child', choices: [], parent: 'n1', child_ids: [], depth: 1 },
      },
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => apiResponse,
    });

    const m = forgeBranchTreeMount();
    m._sessionId = 'sess1';
    await m.refresh();

    expect(fetchSpy).toHaveBeenCalledWith('/api/branch/sess1/tree');
    expect(m.loaded).toBe(true);
    expect(m.loading).toBe(false);
    expect(m.error).toBeNull();
    expect(m.nodes).toHaveLength(2);
    expect(m.currentNode).toBe('n2');
  });

  it('refresh HTTP error: sets error, loaded remains false', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 404 });

    const m = forgeBranchTreeMount();
    m._sessionId = 'sess1';
    await m.refresh();

    expect(m.loaded).toBe(false);
    expect(m.loading).toBe(false);
    expect(m.error).toBe('HTTP 404');
  });

  it('refresh network error: sets error from thrown Error', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('Network failure'));

    const m = forgeBranchTreeMount();
    m._sessionId = 'sess1';
    await m.refresh();

    expect(m.loaded).toBe(false);
    expect(m.loading).toBe(false);
    expect(m.error).toBe('Network failure');
  });

  it('refresh clears stale error on next successful call', async () => {
    fetchSpy
      .mockRejectedValueOnce(new Error('Fail'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'sess1', root: 'n1', current: 'n1',
          nodes: { n1: { id: 'n1', text: 'R', choices: [], parent: null, child_ids: [], depth: 0 } },
        }),
      });

    const m = forgeBranchTreeMount();
    m._sessionId = 'sess1';

    await m.refresh();
    expect(m.error).toBe('Fail');

    await m.refresh();
    expect(m.error).toBeNull();
    expect(m.loaded).toBe(true);
  });
});
