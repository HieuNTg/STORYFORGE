/**
 * Tests for ConfigPanel Alpine.data factory.
 *
 * Covers:
 *   - Initial expanded / dirty / errors state
 *   - toggle(group) flips expansion
 *   - notifyChange marks the OWNING group dirty (not the passed-in group)
 *   - Validation populates and clears errors
 *   - aria-expanded / aria-invalid helpers
 *   - helpIdFor slugifies field keys safely
 *   - anyDirty reflects per-group dirty flags
 *   - sf:config-changed dispatch payload
 *   - DEFAULT_CONFIG_DESCRIPTORS contract
 */

import { describe, it, expect, vi } from 'vitest';
import {
  configPanel,
  DEFAULT_CONFIG_DESCRIPTORS,
  ConfigDescriptor,
} from '../ConfigPanel';

const makeDescriptors = (): ConfigDescriptor[] => [
  {
    id: 'llm',
    title: 'config.section.llm',
    fields: [
      { key: 'layer1_model', label: 'Layer 1', type: 'text' },
      {
        key: 'chapter_batch_size',
        label: 'Batch',
        type: 'number',
        validate: (v) => (typeof v === 'number' && v > 0 ? undefined : 'Must be > 0'),
      },
    ],
  },
  {
    id: 'l2',
    title: 'config.section.l2',
    fields: [
      { key: 'l2_consistency_engine', label: 'L2 engine', type: 'toggle' },
    ],
  },
];

describe('configPanel', () => {
  it('expands the default section and collapses the rest', () => {
    const p = configPanel({ descriptors: makeDescriptors() });
    expect(p.isExpanded('llm')).toBe(true);
    expect(p.isExpanded('l2')).toBe(false);
    expect(p.ariaExpanded('llm')).toBe('true');
    expect(p.ariaExpanded('l2')).toBe('false');
  });

  it('respects an explicit defaultExpanded list', () => {
    const p = configPanel({
      descriptors: makeDescriptors(),
      defaultExpanded: ['l2'],
    });
    expect(p.isExpanded('llm')).toBe(false);
    expect(p.isExpanded('l2')).toBe(true);
  });

  it('starts with every section clean and no errors', () => {
    const p = configPanel({ descriptors: makeDescriptors() });
    expect(p.isDirty('llm')).toBe(false);
    expect(p.isDirty('l2')).toBe(false);
    expect(p.anyDirty).toBe(false);
    expect(p.errors).toEqual({});
  });

  describe('toggle', () => {
    it('flips the expanded flag for the given group', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      p.toggle('l2');
      expect(p.isExpanded('l2')).toBe(true);
      p.toggle('l2');
      expect(p.isExpanded('l2')).toBe(false);
    });
  });

  describe('notifyChange', () => {
    it('marks the owning group dirty (resolves field → group regardless of arg)', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      // Pass 'l2' even though chapter_batch_size belongs to 'llm' — owner wins.
      p.notifyChange('l2', 'chapter_batch_size', 5);
      expect(p.isDirty('llm')).toBe(true);
      expect(p.isDirty('l2')).toBe(false);
      expect(p.anyDirty).toBe(true);
    });

    it('runs validator and sets errors[fieldKey] on failure', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      p.notifyChange('llm', 'chapter_batch_size', -1);
      expect(p.errors['chapter_batch_size']).toBe('Must be > 0');
      expect(p.ariaInvalid('chapter_batch_size')).toBe('true');
      expect(p.errorFor('chapter_batch_size')).toBe('Must be > 0');
    });

    it('clears a prior error when validation passes', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      p.notifyChange('llm', 'chapter_batch_size', -1);
      expect(p.errors['chapter_batch_size']).toBeDefined();
      p.notifyChange('llm', 'chapter_batch_size', 5);
      expect(p.errors['chapter_batch_size']).toBeUndefined();
      expect(p.ariaInvalid('chapter_batch_size')).toBeUndefined();
    });

    it('dispatches sf:config-changed with the resolved owner group', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      const dispatch = vi.fn();
      Object.assign(p, { $dispatch: dispatch });
      p.notifyChange('llm', 'layer1_model', 'gpt-5');
      expect(dispatch).toHaveBeenCalledWith('sf:config-changed', {
        group: 'llm',
        field: 'layer1_model',
        value: 'gpt-5',
      });
    });

    it('falls back to the passed group when the field is unknown', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      p.notifyChange('l2', 'unregistered_field', 'x');
      expect(p.isDirty('l2')).toBe(true);
    });

    it('does not throw when $dispatch is absent', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      expect(() => p.notifyChange('llm', 'layer1_model', 'x')).not.toThrow();
    });
  });

  describe('helpIdFor', () => {
    it('returns a DOM-safe id for valid keys', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      expect(p.helpIdFor('layer1_model')).toBe('sf-cfg-help-layer1_model');
    });

    it('replaces unsafe characters with hyphens', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      expect(p.helpIdFor('foo.bar/baz')).toBe('sf-cfg-help-foo-bar-baz');
    });
  });

  describe('reset', () => {
    it('clears every dirty flag and every error', () => {
      const p = configPanel({ descriptors: makeDescriptors() });
      p.notifyChange('llm', 'chapter_batch_size', -1);
      p.notifyChange('l2', 'l2_consistency_engine', true);
      expect(p.anyDirty).toBe(true);
      expect(Object.keys(p.errors).length).toBeGreaterThan(0);
      p.reset();
      expect(p.anyDirty).toBe(false);
      expect(p.errors).toEqual({});
    });
  });

  describe('empty descriptors', () => {
    it('produces a usable, inert panel', () => {
      const p = configPanel({ descriptors: [] });
      expect(p.anyDirty).toBe(false);
      expect(p.descriptors).toEqual([]);
    });
  });
});

describe('DEFAULT_CONFIG_DESCRIPTORS', () => {
  it('covers the canonical groups expected by the Pipeline page', () => {
    const ids = DEFAULT_CONFIG_DESCRIPTORS.map((d) => d.id);
    expect(ids).toEqual(['llm', 'pipeline', 'l2']);
  });

  it('is frozen so consumers cannot mutate the descriptor table at runtime', () => {
    expect(Object.isFrozen(DEFAULT_CONFIG_DESCRIPTORS)).toBe(true);
  });

  it('every field carries a key, label, and type', () => {
    for (const section of DEFAULT_CONFIG_DESCRIPTORS) {
      for (const field of section.fields) {
        expect(field.key).toBeTruthy();
        expect(field.label).toBeTruthy();
        expect(field.type).toBeTruthy();
      }
    }
  });
});
