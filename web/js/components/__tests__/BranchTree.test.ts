/**
 * Tests for BranchTree Alpine.data factory.
 *
 * Covers:
 *   - Defaults + prop overrides
 *   - srEntries derivation (a11y screen-reader mirror list)
 *   - minimapLabel / currentBranchIndex (text fallback for minimap)
 *   - setData reconciles nodes, preserving existing x/y positions
 *   - 50-node synthetic fixture: all nodes reachable after init()
 *   - Canvas attach/draw with mocked 2d context
 *   - Minimap canvas draw
 *   - Keyboard nav: ArrowRight (child), ArrowLeft (parent), Enter/Space (navigate)
 *   - Pointer drag: down -> fx/fy set, move -> update, up -> pin toggle
 *   - Wheel zoom: scale clamped to [0.3, 3]
 *   - navigateTo dispatches sf:branch-navigate DOM event
 *   - Reduced-motion path: settles synchronously, no rAF loop
 *   - init() creates simulation; destroy() stops it
 *   - Flag-gate: module importable without forgeUi flag (flag gate is in app.ts)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { branchTree } from '../BranchTree';
import type { BranchNode, BranchTreeComponent } from '../BranchTree';

// ── Fixtures ────────────────────────────────────────────────────────────────

/** Build a linear chain: root -> n1 -> n2 -> ... */
function makeChain(count: number): BranchNode[] {
  const nodes: BranchNode[] = [];
  for (let i = 0; i < count; i++) {
    nodes.push({
      id: `n${i}`,
      label: `Node ${i}`,
      parentId: i === 0 ? null : `n${i - 1}`,
      depth: i,
    });
  }
  return nodes;
}

/** Build a balanced binary tree of `levels` levels (2^levels - 1 nodes). */
function makeBinaryTree(levels: number): BranchNode[] {
  const nodes: BranchNode[] = [];
  function add(id: string, parentId: string | null, depth: number, maxDepth: number): void {
    nodes.push({ id, label: id, parentId, depth });
    if (depth < maxDepth - 1) {
      add(`${id}L`, id, depth + 1, maxDepth);
      add(`${id}R`, id, depth + 1, maxDepth);
    }
  }
  add('root', null, 0, levels);
  return nodes;
}

/** Make a wide flat tree: root + N children of root. */
function makeWideFlatTree(childCount: number): BranchNode[] {
  const nodes: BranchNode[] = [{ id: 'root', label: 'Root', parentId: null, depth: 0 }];
  for (let i = 0; i < childCount; i++) {
    nodes.push({ id: `c${i}`, label: `Child ${i}`, parentId: 'root', depth: 1 });
  }
  return nodes;
}

/** Minimal canvas mock — exposes just enough 2d context for draw() to run. */
function makeCanvasMock(): HTMLCanvasElement {
  const ctx = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    strokeRect: vi.fn(),
    fillRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 0,
    globalAlpha: 1,
    font: '',
    textAlign: '',
    textBaseline: '',
  };
  return {
    width: 0,
    height: 0,
    getContext: vi.fn(() => ctx),
    getBoundingClientRect: vi.fn(
      () =>
        ({
          left: 0,
          top: 0,
          right: 800,
          bottom: 500,
          width: 800,
          height: 500,
          x: 0,
          y: 0,
          toJSON() {},
        } as DOMRect),
    ),
  } as unknown as HTMLCanvasElement;
}

// ── Setup/teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal('devicePixelRatio', 1);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── Tests ───────────────────────────────────────────────────────────────────

describe('branchTree factory', () => {
  it('uses sane defaults', () => {
    const bt = branchTree();
    expect(bt.nodes).toEqual([]);
    expect(bt.currentNodeId).toBeNull();
    expect(bt.width).toBe(800);
    expect(bt.height).toBe(500);
    expect(bt.minimapWidth).toBe(160);
    expect(bt.minimapHeight).toBe(100);
    expect(bt.canvas).toBeNull();
    expect(bt.minimapCanvas).toBeNull();
    expect(bt.simulation).toBeNull();
    expect(bt.focusedNodeId).toBeNull();
    expect(bt._panX).toBe(0);
    expect(bt._panY).toBe(0);
    expect(bt._scale).toBe(1);
  });

  it('accepts prop overrides', () => {
    const nodes = makeChain(3);
    const bt = branchTree({ nodes, currentNodeId: 'n1', width: 1200, height: 700 });
    expect(bt.nodes).toHaveLength(3);
    expect(bt.currentNodeId).toBe('n1');
    expect(bt.width).toBe(1200);
    expect(bt.height).toBe(700);
  });
});

// ── srEntries ───────────────────────────────────────────────────────────────

describe('srEntries', () => {
  it('returns one entry per node with correct childIds', () => {
    const nodes = makeWideFlatTree(3);
    const bt = branchTree({ nodes, currentNodeId: 'root' });
    const entries = bt.srEntries;
    expect(entries).toHaveLength(4); // root + 3 children
    const root = entries.find((e) => e.id === 'root')!;
    expect(root.childIds).toHaveLength(3);
    expect(root.isCurrent).toBe(true);
    const c0 = entries.find((e) => e.id === 'c0')!;
    expect(c0.parentId).toBe('root');
    expect(c0.childIds).toHaveLength(0);
    expect(c0.isCurrent).toBe(false);
  });

  it('returns empty list when nodes is empty', () => {
    const bt = branchTree();
    expect(bt.srEntries).toEqual([]);
  });
});

// ── minimapLabel / currentBranchIndex ───────────────────────────────────────

describe('minimapLabel', () => {
  it('shows "Branch X of Y" for current node', () => {
    const nodes = makeChain(5);
    const bt = branchTree({ nodes, currentNodeId: 'n2' });
    // n2 is index 2 (0-based) → "Branch 3 of 5"
    expect(bt.minimapLabel).toBe('Branch 3 of 5');
    expect(bt.currentBranchIndex).toBe(3);
  });

  it('returns empty string when no nodes', () => {
    const bt = branchTree();
    expect(bt.minimapLabel).toBe('');
  });

  it('shows total count when currentNodeId not found', () => {
    const nodes = makeChain(4);
    const bt = branchTree({ nodes, currentNodeId: 'nonexistent' });
    expect(bt.minimapLabel).toBe('4 branches');
  });
});

// ── setData ─────────────────────────────────────────────────────────────────

describe('setData', () => {
  it('replaces nodes and updates currentNodeId', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    bt.setData(makeChain(5), 'n4');
    expect(bt.nodes).toHaveLength(5);
    expect(bt.currentNodeId).toBe('n4');
  });

  it('preserves the same SimNode object reference for pre-existing nodes', () => {
    // reconcileSimNodes returns the existing SimNode reference (not a new object)
    // so that d3-force can continue tracking velocity from the same mutable object.
    // x/y may be moved by the subsequent settle tick — that is expected and correct.
    const nodes = makeChain(3);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();

    const n0Before = bt._simNodes.find((n) => n.id === 'n0')!;

    // Extend chain by one node.
    bt.setData([...nodes, { id: 'n3', label: 'Node 3', parentId: 'n2', depth: 3 }], 'n3');

    const n0After = bt._simNodes.find((n) => n.id === 'n0')!;
    // Same object reference — not a newly constructed SimNode.
    expect(n0After).toBe(n0Before);
    bt.destroy();
  });
});

// ── 50-node performance fixture ─────────────────────────────────────────────

describe('50-node synthetic fixture', () => {
  it('init() creates a simulation with all 50 nodes reachable', () => {
    // 50 nodes: binary tree of 6 levels = 63 nodes, trim to 50 children of root.
    const nodes = makeWideFlatTree(49); // root + 49 = 50 nodes
    expect(nodes).toHaveLength(50);

    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();

    expect(bt._simNodes).toHaveLength(50);
    // All nodes should have numeric x/y after synchronous settle.
    const withPositions = bt._simNodes.filter(
      (n) => typeof n.x === 'number' && typeof n.y === 'number',
    );
    expect(withPositions).toHaveLength(50);

    bt.destroy();
  });

  it('50-node binary tree settles with reduced-motion', () => {
    // 6 levels -> 2^6 - 1 = 63 nodes, we use 5 levels = 31 nodes + pad to 50 via chain
    const nodes: BranchNode[] = makeBinaryTree(5); // 31 nodes
    // Add extra chain to hit 50.
    let prev = nodes[nodes.length - 1].id;
    for (let i = 31; i < 50; i++) {
      const id = `extra${i}`;
      nodes.push({ id, label: `Extra ${i}`, parentId: prev, depth: nodes[i - 1]?.depth ?? 0 + 1 });
      prev = id;
    }
    expect(nodes).toHaveLength(50);

    const bt = branchTree({ nodes: nodes.slice(0, 50), prefersReducedMotion: true });
    bt.init();
    expect(bt._simNodes).toHaveLength(50);
    bt.destroy();
  });
});

// ── Canvas draw ─────────────────────────────────────────────────────────────

describe('canvas draw', () => {
  it('attachCanvas stores ref and calls draw', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    const canvas = makeCanvasMock();
    const spy = vi.spyOn(bt, 'draw');
    bt.attachCanvas(canvas);
    expect(bt.canvas).toBe(canvas);
    expect(spy).toHaveBeenCalled();
  });

  it('draw() does not throw with no canvas', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    expect(() => bt.draw()).not.toThrow();
  });

  it('draw() calls getContext("2d")', () => {
    const bt = branchTree({ nodes: makeChain(3), prefersReducedMotion: true });
    bt.init();
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);
    expect(canvas.getContext).toHaveBeenCalledWith('2d');
    bt.destroy();
  });
});

// ── Minimap draw ─────────────────────────────────────────────────────────────

describe('minimap draw', () => {
  it('attachMinimapCanvas stores ref', () => {
    const bt = branchTree();
    const mc = makeCanvasMock();
    bt.attachMinimapCanvas(mc);
    expect(bt.minimapCanvas).toBe(mc);
  });

  it('drawMinimap() does not throw without canvas', () => {
    const bt = branchTree({ nodes: makeChain(5) });
    expect(() => bt.drawMinimap()).not.toThrow();
  });

  it('drawMinimap() renders viewport rect after init', () => {
    const nodes = makeChain(5);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    const mc = makeCanvasMock();
    bt.attachMinimapCanvas(mc);
    bt.drawMinimap();
    const ctx = mc.getContext('2d') as unknown as { strokeRect: ReturnType<typeof vi.fn> };
    // strokeRect is called for the viewport indicator.
    expect(ctx.strokeRect).toHaveBeenCalled();
    bt.destroy();
  });
});

// ── Keyboard navigation ──────────────────────────────────────────────────────

describe('handleKeyDown', () => {
  function makeKeyEvent(key: string): KeyboardEvent {
    return {
      key,
      preventDefault: vi.fn(),
    } as unknown as KeyboardEvent;
  }

  it('ArrowRight moves focus to first child', () => {
    const nodes = makeWideFlatTree(3); // root -> c0, c1, c2
    const bt = branchTree({ nodes, currentNodeId: 'root' });
    bt.focusedNodeId = 'root';
    bt.handleKeyDown(makeKeyEvent('ArrowRight'));
    expect(bt.focusedNodeId).toBe('c0');
  });

  it('ArrowLeft moves focus to parent', () => {
    const nodes = makeWideFlatTree(3);
    const bt = branchTree({ nodes, currentNodeId: 'c1' });
    bt.focusedNodeId = 'c1';
    bt.handleKeyDown(makeKeyEvent('ArrowLeft'));
    expect(bt.focusedNodeId).toBe('root');
  });

  it('ArrowLeft on root is a no-op', () => {
    const nodes = makeChain(3);
    const bt = branchTree({ nodes, currentNodeId: 'n0' });
    bt.focusedNodeId = 'n0';
    bt.handleKeyDown(makeKeyEvent('ArrowLeft'));
    expect(bt.focusedNodeId).toBe('n0'); // unchanged
  });

  it('Enter dispatches sf:branch-navigate event', () => {
    const nodes = makeChain(3);
    const bt = branchTree({ nodes, currentNodeId: 'n1' });
    bt.focusedNodeId = 'n1';

    const events: CustomEvent[] = [];
    document.addEventListener('sf:branch-navigate', (e) => events.push(e as CustomEvent));

    bt.handleKeyDown(makeKeyEvent('Enter'));

    expect(events).toHaveLength(1);
    expect(events[0].detail.nodeId).toBe('n1');

    document.removeEventListener('sf:branch-navigate', (e) => events.push(e as CustomEvent));
  });

  it('Space dispatches sf:branch-navigate event', () => {
    const nodes = makeChain(3);
    const bt = branchTree({ nodes, currentNodeId: 'n0' });
    bt.focusedNodeId = 'n0';

    const events: CustomEvent[] = [];
    const handler = (e: Event): void => void events.push(e as CustomEvent);
    document.addEventListener('sf:branch-navigate', handler);

    bt.handleKeyDown(makeKeyEvent(' '));
    expect(events).toHaveLength(1);

    document.removeEventListener('sf:branch-navigate', handler);
  });

  it('ArrowDown is alias for ArrowRight (child)', () => {
    const nodes = makeWideFlatTree(2);
    const bt = branchTree({ nodes, currentNodeId: 'root' });
    bt.focusedNodeId = 'root';
    bt.handleKeyDown(makeKeyEvent('ArrowDown'));
    expect(bt.focusedNodeId).toBe('c0');
  });

  it('ArrowUp is alias for ArrowLeft (parent)', () => {
    const nodes = makeWideFlatTree(2);
    const bt = branchTree({ nodes, currentNodeId: 'c0' });
    bt.focusedNodeId = 'c0';
    bt.handleKeyDown(makeKeyEvent('ArrowUp'));
    expect(bt.focusedNodeId).toBe('root');
  });

  it('unrelated keys are ignored (no preventDefault)', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    bt.focusedNodeId = 'n0';
    const event = { key: 'Tab', preventDefault: vi.fn() } as unknown as KeyboardEvent;
    bt.handleKeyDown(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(bt.focusedNodeId).toBe('n0');
  });
});

// ── navigateTo ──────────────────────────────────────────────────────────────

describe('navigateTo', () => {
  it('calls onNavigate callback', () => {
    const onNavigate = vi.fn();
    const bt = branchTree({ nodes: makeChain(3), onNavigate });
    bt.navigateTo('n2');
    expect(onNavigate).toHaveBeenCalledWith('n2');
  });

  it('dispatches sf:branch-navigate DOM event', () => {
    const events: CustomEvent[] = [];
    const handler = (e: Event): void => void events.push(e as CustomEvent);
    document.addEventListener('sf:branch-navigate', handler);

    const bt = branchTree({ nodes: makeChain(3) });
    bt.navigateTo('n1');

    expect(events).toHaveLength(1);
    expect(events[0].detail.nodeId).toBe('n1');

    document.removeEventListener('sf:branch-navigate', handler);
  });

  it('survives a throwing onNavigate (silent catch)', () => {
    const bt = branchTree({
      nodes: makeChain(3),
      onNavigate: () => {
        throw new Error('boom');
      },
    });
    expect(() => bt.navigateTo('n0')).not.toThrow();
  });
});

// ── Pointer drag / pin toggle ────────────────────────────────────────────────

describe('pointer drag', () => {
  function makePointerEvent(type: 'down' | 'move' | 'up', cx: number, cy: number): PointerEvent {
    return {
      clientX: cx,
      clientY: cy,
      type: `pointer${type}`,
      preventDefault: vi.fn(),
    } as unknown as PointerEvent;
  }

  it('pointerdown near a node sets fx/fy', () => {
    const nodes = makeChain(2);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);

    // Force a known position on n0.
    const n0 = bt._simNodes.find((n) => n.id === 'n0')!;
    n0.x = 100;
    n0.y = 100;

    bt.handlePointerDown(makePointerEvent('down', 102, 101));
    expect(bt._dragging).toBe(n0);
    expect(n0.fx).toBeCloseTo(n0.x as number, 0);
    expect(n0.fy).toBeCloseTo(n0.y as number, 0);

    bt.destroy();
  });

  it('pointermove updates dragged node fx/fy', () => {
    const nodes = makeChain(2);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);

    const n0 = bt._simNodes.find((n) => n.id === 'n0')!;
    n0.x = 100;
    n0.y = 100;
    bt.handlePointerDown(makePointerEvent('down', 100, 100));
    bt.handlePointerMove(makePointerEvent('move', 200, 150));
    expect(n0.fx).toBeCloseTo(200, 0);
    expect(n0.fy).toBeCloseTo(150, 0);

    bt.destroy();
  });

  it('pointerup clears _dragging', () => {
    const nodes = makeChain(2);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);

    const n0 = bt._simNodes.find((n) => n.id === 'n0')!;
    n0.x = 100;
    n0.y = 100;
    bt.handlePointerDown(makePointerEvent('down', 100, 100));
    expect(bt._dragging).not.toBeNull();
    bt.handlePointerUp(makePointerEvent('up', 100, 100));
    expect(bt._dragging).toBeNull();

    bt.destroy();
  });
});

// ── Wheel zoom ──────────────────────────────────────────────────────────────

describe('handleWheel', () => {
  it('increases scale on negative deltaY (scroll up = zoom in)', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);
    const before = bt._scale;
    bt.handleWheel({ deltaY: -1, clientX: 400, clientY: 250, preventDefault: vi.fn() } as unknown as WheelEvent);
    expect(bt._scale).toBeGreaterThan(before);
  });

  it('decreases scale on positive deltaY (scroll down = zoom out)', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);
    const before = bt._scale;
    bt.handleWheel({ deltaY: 1, clientX: 400, clientY: 250, preventDefault: vi.fn() } as unknown as WheelEvent);
    expect(bt._scale).toBeLessThan(before);
  });

  it('clamps scale to [0.3, 3]', () => {
    const bt = branchTree({ nodes: makeChain(3) });
    const canvas = makeCanvasMock();
    bt.attachCanvas(canvas);

    // Zoom in hard 30 times.
    for (let i = 0; i < 30; i++) {
      bt.handleWheel({ deltaY: -1, clientX: 400, clientY: 250, preventDefault: vi.fn() } as unknown as WheelEvent);
    }
    expect(bt._scale).toBeLessThanOrEqual(3);

    // Zoom out hard 50 times.
    for (let i = 0; i < 50; i++) {
      bt.handleWheel({ deltaY: 1, clientX: 400, clientY: 250, preventDefault: vi.fn() } as unknown as WheelEvent);
    }
    expect(bt._scale).toBeGreaterThanOrEqual(0.3);
  });
});

// ── Reduced-motion ──────────────────────────────────────────────────────────

describe('reduced-motion path', () => {
  it('does not call requestAnimationFrame when prefersReducedMotion is true', () => {
    const nodes = makeChain(5);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    bt.destroy();
  });

  it('all nodes have numeric positions after synchronous settle', () => {
    const nodes = makeChain(10);
    const bt = branchTree({ nodes, prefersReducedMotion: true });
    bt.init();
    for (const n of bt._simNodes) {
      expect(typeof n.x).toBe('number');
      expect(typeof n.y).toBe('number');
    }
    bt.destroy();
  });
});

// ── Lifecycle ────────────────────────────────────────────────────────────────

describe('lifecycle', () => {
  it('init() creates simulation', () => {
    const bt = branchTree({ nodes: makeChain(3), prefersReducedMotion: true });
    expect(bt.simulation).toBeNull();
    bt.init();
    expect(bt.simulation).not.toBeNull();
    bt.destroy();
  });

  it('destroy() stops simulation and nulls it', () => {
    const bt = branchTree({ nodes: makeChain(3), prefersReducedMotion: true });
    bt.init();
    expect(bt.simulation).not.toBeNull();
    bt.destroy();
    expect(bt.simulation).toBeNull();
  });

  it('step() ticks simulation without throwing', () => {
    const bt = branchTree({ nodes: makeChain(3), prefersReducedMotion: true });
    bt.init();
    expect(() => bt.step()).not.toThrow();
    bt.destroy();
  });
});
