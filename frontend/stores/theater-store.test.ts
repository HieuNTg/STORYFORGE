/**
 * Tests for theater-store `applyDone` quality-score mapping.
 *
 * This sprint fixed the backend `{layer, overall, coherence, character, drama,
 * writing}` shape to map into the canonical gauge with Vietnamese dimension
 * labels (Mạch lạc / Nhân vật / Kịch tính / Văn phong) and to pick the
 * highest-layer entry as the canonical snapshot.
 */

import { describe, it, beforeEach, expect } from "vitest";
import { useTheaterStore } from "./theater-store";

const VN_LABELS = ["Mạch lạc", "Nhân vật", "Kịch tính", "Văn phong"];

beforeEach(() => {
  useTheaterStore.getState().reset();
});

describe("theater-store applyDone — quality scores", () => {
  it("maps a single backend quality entry into canonical gauge + 4 VN dimensions", () => {
    useTheaterStore.getState().applyDone({
      data: {
        quality: [
          {
            layer: 1,
            overall: 0.7,
            coherence: 0.6,
            character: 0.65,
            drama: 0.75,
            writing: 0.8,
          },
        ],
      },
    });
    const q = useTheaterStore.getState().quality;
    expect(q.value).toBe(0.7);
    expect(q.layer).toBe(1);
    expect(q.dimensions).toHaveLength(4);
    expect(q.dimensions.map((d) => d.name)).toEqual(VN_LABELS);
  });

  it("picks the highest-layer entry when multiple layers are reported", () => {
    useTheaterStore.getState().applyDone({
      data: {
        quality: [
          {
            layer: 1,
            overall: 0.7,
            coherence: 0.6,
            character: 0.65,
            drama: 0.75,
            writing: 0.8,
          },
          {
            layer: 2,
            overall: 0.85,
            coherence: 0.82,
            character: 0.88,
            drama: 0.84,
            writing: 0.87,
          },
        ],
      },
    });
    const q = useTheaterStore.getState().quality;
    expect(q.value).toBe(0.85);
    expect(q.layer).toBe(2);
    // Dimensions came from the layer-2 entry.
    const byName = Object.fromEntries(q.dimensions.map((d) => [d.name, d.value]));
    expect(byName["Mạch lạc"]).toBeCloseTo(0.82);
    expect(byName["Văn phong"]).toBeCloseTo(0.87);
  });

  it("leaves quality untouched when quality array is empty and no quality_score", () => {
    // Grounded on theater-store.ts:470 (`qList.length > 0`) and :497-505
    // (the else-if requires `Number.isFinite(payload.data.quality_score)`).
    // With neither, no `set({ quality: ... })` call runs.
    const before = useTheaterStore.getState().quality;
    useTheaterStore.getState().applyDone({ data: { quality: [] } });
    const after = useTheaterStore.getState().quality;
    expect(after).toEqual(before);
    expect(after.value).toBe(0);
    expect(after.dimensions).toEqual([]);
  });

  it("falls back to legacy {name, value} shape when backend keys are absent", () => {
    // Grounded on theater-store.ts:477-483 — when buildDimensionsFromBackend
    // returns [] (no coherence/character/drama/writing fields), the code falls
    // back to legacyDims built from {name, value} pairs. `overall` is undefined
    // on the legacy entry, so the value comes from the dimensions average:
    // single entry [0.6] → average 0.6.
    useTheaterStore.getState().applyDone({
      data: {
        quality: [{ name: "Overall", value: 0.6 }],
      },
    });
    const q = useTheaterStore.getState().quality;
    expect(q.value).toBeCloseTo(0.6);
    expect(q.dimensions).toEqual([{ name: "Overall", value: 0.6 }]);
  });
});
