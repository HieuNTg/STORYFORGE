/**
 * Tests for CharacterGraph Alpine.data factory.
 *
 * Covers:
 *   - Defaults + prop overrides
 *   - srEntries derivation (per-character edge mirror for SR list)
 *   - setData reconciles nodes preserving x/y positions
 *   - Canvas attach/draw with mocked 2d context
 *   - Pointer drag: down → fx/fy set, move → fx/fy update, up → clear
 *   - Reduced-motion: simulation settles synchronously, no rAF loop
 *   - Lifecycle: init creates simulation; destroy stops it
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { characterGraph } from '../CharacterGraph';
import type { CharacterEdge, CharacterNode } from '../CharacterGraph';

const chars: CharacterNode[] = [
  { id: 'an', name: 'An' },
  { id: 'binh', name: 'Bình' },
  { id: 'cuong', name: 'Cường' },
];

const rels: CharacterEdge[] = [
  { sourceId: 'an', targetId: 'binh', type: 'ally', intensity: 1 },
  { sourceId: 'an', targetId: 'cuong', type: 'rival', intensity: 0.66 },
  { sourceId: 'binh', targetId: 'cuong', type: 'enemy', intensity: 0.33 },
];

/** Minimal canvas mock — exposes a fake 2d context whose calls we don't care about. */
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
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 0,
    globalAlpha: 1,
    font: '',
    textAlign: '',
    textBaseline: '',
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: vi.fn(() => ctx),
    getBoundingClientRect: vi.fn(() => ({ left: 0, top: 0, right: 600, bottom: 400, width: 600, height: 400, x: 0, y: 0, toJSON() {} } as DOMRect)),
  } as unknown as HTMLCanvasElement;
  return canvas;
}

beforeEach(() => {
  // Stop the rAF loop from blowing up; we never want it scheduled in tests.
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('characterGraph', () => {
  it('uses sane defaults', () => {
    const g = characterGraph();
    expect(g.characters).toEqual([]);
    expect(g.relationships).toEqual([]);
    expect(g.compact).toBe(false);
    expect(g.interactive).toBe(true);
    expect(g.width).toBe(600);
    expect(g.height).toBe(400);
    expect(g.canvas).toBeNull();
    expect(g.simulation).toBeNull();
  });

  it('honors prop overrides', () => {
    const g = characterGraph({
      characters: chars,
      relationships: rels,
      compact: true,
      interactive: false,
      width: 800,
      height: 500,
      prefersReducedMotion: true,
    });
    expect(g.characters).toHaveLength(3);
    expect(g.relationships).toHaveLength(3);
    expect(g.compact).toBe(true);
    expect(g.interactive).toBe(false);
    expect(g.width).toBe(800);
    expect(g.height).toBe(500);
    expect(g.prefersReducedMotion).toBe(true);
  });

  describe('srEntries', () => {
    it('emits one entry per character with edges naming the other end', () => {
      const g = characterGraph({ characters: chars, relationships: rels });
      const entries = g.srEntries;
      expect(entries).toHaveLength(3);

      const an = entries.find((e) => e.name === 'An');
      expect(an?.edges.map((e) => e.otherName).sort()).toEqual(['Bình', 'Cường']);

      const binh = entries.find((e) => e.name === 'Bình');
      expect(binh?.edges).toHaveLength(2);

      const cuong = entries.find((e) => e.name === 'Cường');
      expect(cuong?.edges).toHaveLength(2);
    });

    it('preserves edge type and intensity in the mirror', () => {
      const g = characterGraph({ characters: chars, relationships: rels });
      const an = g.srEntries.find((e) => e.name === 'An')!;
      const toBinh = an.edges.find((e) => e.otherName === 'Bình')!;
      expect(toBinh.type).toBe('ally');
      expect(toBinh.intensity).toBe(1);
    });

    it('returns empty edges for characters with no relationships', () => {
      const g = characterGraph({
        characters: [{ id: 'lonely', name: 'Lonely' }],
        relationships: [],
      });
      expect(g.srEntries).toEqual([{ name: 'Lonely', edges: [] }]);
    });
  });

  describe('lifecycle', () => {
    it('init creates a simulation and seeds positions near center', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      expect(g.simulation).not.toBeNull();
      expect(g.nodes).toHaveLength(3);
      for (const n of g.nodes) {
        expect(typeof n.x).toBe('number');
        expect(typeof n.y).toBe('number');
      }
    });

    it('destroy stops the simulation and clears rAF', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      const sim = g.simulation!;
      const stopSpy = vi.spyOn(sim, 'stop');
      g.destroy();
      expect(stopSpy).toHaveBeenCalled();
      expect(g.simulation).toBeNull();
    });

    it('reduced-motion path settles synchronously, no rAF scheduled', () => {
      const rafSpy = vi.fn(() => 1);
      vi.stubGlobal('requestAnimationFrame', rafSpy);
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      expect(rafSpy).not.toHaveBeenCalled();
      expect(g.simulation!.alpha()).toBeLessThan(g.simulation!.alphaMin() + 0.001);
    });
  });

  describe('setData', () => {
    it('reuses the same SimNode object when id survives reconcile', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      const anBefore = g.nodes.find((n) => n.id === 'an')!;

      // Drop Cường, keep An + Bình, change Bình's name.
      g.setData(
        [
          { id: 'an', name: 'An' },
          { id: 'binh', name: 'Bình (updated)' },
        ],
        [{ sourceId: 'an', targetId: 'binh', type: 'neutral', intensity: 0.5 }],
      );

      expect(g.nodes).toHaveLength(2);
      const anAfter = g.nodes.find((n) => n.id === 'an')!;
      // Same object reference → x/y/vx/vy continuity preserved across reconcile.
      expect(anAfter).toBe(anBefore);
      const binhAfter = g.nodes.find((n) => n.id === 'binh')!;
      expect(binhAfter.name).toBe('Bình (updated)');
    });

    it('drops links whose endpoints no longer exist', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      g.setData([{ id: 'an', name: 'An' }], []);
      expect(g.links).toHaveLength(0);
    });
  });

  describe('canvas + draw', () => {
    it('attachCanvas stores the ref and immediately draws', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      const canvas = makeCanvasMock();
      g.attachCanvas(canvas);
      expect(g.canvas).toBe(canvas);
      expect(canvas.getContext).toHaveBeenCalledWith('2d');
    });

    it('draw is a no-op when canvas not attached', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      expect(() => g.draw()).not.toThrow();
    });

    it('sets canvas backing store to width*dpr by height*dpr', () => {
      vi.stubGlobal('devicePixelRatio', 2);
      const g = characterGraph({
        characters: chars,
        relationships: rels,
        prefersReducedMotion: true,
        width: 300,
        height: 200,
      });
      g.init();
      const canvas = makeCanvasMock();
      g.attachCanvas(canvas);
      expect(canvas.width).toBe(600);
      expect(canvas.height).toBe(400);
    });
  });

  describe('pointer drag', () => {
    it('handlePointerDown fixes the nearest node and bumps alphaTarget', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      g.attachCanvas(makeCanvasMock());
      const an = g.nodes.find((n) => n.id === 'an')!;
      an.x = 100;
      an.y = 100;
      const alphaTargetSpy = vi.spyOn(g.simulation!, 'alphaTarget');

      g.handlePointerDown({ clientX: 100, clientY: 100 } as PointerEvent);
      expect(an.fx).toBe(100);
      expect(an.fy).toBe(100);
      expect(g._dragging).toBe(an);
      expect(alphaTargetSpy).toHaveBeenCalledWith(0.3);
    });

    it('handlePointerDown is a no-op when not interactive', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true, interactive: false });
      g.init();
      g.attachCanvas(makeCanvasMock());
      const an = g.nodes.find((n) => n.id === 'an')!;
      an.x = 100;
      an.y = 100;
      g.handlePointerDown({ clientX: 100, clientY: 100 } as PointerEvent);
      expect(g._dragging).toBeNull();
      expect(an.fx).toBeUndefined();
    });

    it('handlePointerDown ignores pointers far from any node', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      g.attachCanvas(makeCanvasMock());
      for (const n of g.nodes) {
        n.x = 50;
        n.y = 50;
      }
      g.handlePointerDown({ clientX: 500, clientY: 500 } as PointerEvent);
      expect(g._dragging).toBeNull();
    });

    it('handlePointerMove updates fx/fy on the dragged node', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      g.attachCanvas(makeCanvasMock());
      const an = g.nodes.find((n) => n.id === 'an')!;
      an.x = 100;
      an.y = 100;
      g.handlePointerDown({ clientX: 100, clientY: 100 } as PointerEvent);
      g.handlePointerMove({ clientX: 250, clientY: 175 } as PointerEvent);
      expect(an.fx).toBe(250);
      expect(an.fy).toBe(175);
    });

    it('handlePointerUp clears fx/fy and resets alphaTarget', () => {
      const g = characterGraph({ characters: chars, relationships: rels, prefersReducedMotion: true });
      g.init();
      g.attachCanvas(makeCanvasMock());
      const an = g.nodes.find((n) => n.id === 'an')!;
      an.x = 100;
      an.y = 100;
      g.handlePointerDown({ clientX: 100, clientY: 100 } as PointerEvent);
      const alphaTargetSpy = vi.spyOn(g.simulation!, 'alphaTarget');
      g.handlePointerUp({} as PointerEvent);
      expect(an.fx).toBeNull();
      expect(an.fy).toBeNull();
      expect(g._dragging).toBeNull();
      expect(alphaTargetSpy).toHaveBeenCalledWith(0);
    });
  });
});
