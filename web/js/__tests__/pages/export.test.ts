/**
 * pages/export.test.ts
 *
 * Unit tests for forgeExportCards() Alpine.data factory and FORGE_EXPORT_FORMATS.
 *
 * Covers:
 *   - FORGE_EXPORT_FORMATS has 4 entries (pdf, epub, html, zip)
 *   - Default state shape
 *   - selectFormat(): opens panel with new format
 *   - selectFormat(): toggles panel when same format re-selected
 *   - selectFormat(): switches to new format (panelVisible stays true)
 *   - closePanel(): resets selectedFormat + panelVisible
 */

import { describe, it, expect } from 'vitest';
import { forgeExportCards, FORGE_EXPORT_FORMATS } from '../../pages/export';

describe('FORGE_EXPORT_FORMATS', () => {
  it('has exactly 4 formats', () => {
    expect(FORGE_EXPORT_FORMATS).toHaveLength(4);
  });

  it('contains pdf, epub, html, zip ids', () => {
    const ids = FORGE_EXPORT_FORMATS.map(f => f.id);
    expect(ids).toContain('pdf');
    expect(ids).toContain('epub');
    expect(ids).toContain('html');
    expect(ids).toContain('zip');
  });

  it('each format has id, label, hint, color', () => {
    for (const fmt of FORGE_EXPORT_FORMATS) {
      expect(fmt.id).toBeTruthy();
      expect(fmt.label).toBeTruthy();
      expect(fmt.hint).toBeTruthy();
      expect(fmt.color).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});

describe('forgeExportCards', () => {
  it('returns correct default state', () => {
    const c = forgeExportCards();
    expect(c.selectedFormat).toBeNull();
    expect(c.panelVisible).toBe(false);
    expect(c.formats).toBe(FORGE_EXPORT_FORMATS);
  });

  it('selectFormat() sets format and opens panel', () => {
    const c = forgeExportCards();
    c.selectFormat('pdf');
    expect(c.selectedFormat).toBe('pdf');
    expect(c.panelVisible).toBe(true);
  });

  it('selectFormat() toggles panel when same format selected twice', () => {
    const c = forgeExportCards();
    c.selectFormat('pdf');
    expect(c.panelVisible).toBe(true);
    c.selectFormat('pdf');
    expect(c.panelVisible).toBe(false);
    expect(c.selectedFormat).toBe('pdf');
  });

  it('selectFormat() re-opens panel on third click of same format', () => {
    const c = forgeExportCards();
    c.selectFormat('pdf');
    c.selectFormat('pdf'); // close
    c.selectFormat('pdf'); // re-open
    expect(c.panelVisible).toBe(true);
  });

  it('selectFormat() switches to new format without closing panel', () => {
    const c = forgeExportCards();
    c.selectFormat('pdf');
    c.selectFormat('epub');
    expect(c.selectedFormat).toBe('epub');
    expect(c.panelVisible).toBe(true);
  });

  it('closePanel() hides panel and clears selectedFormat', () => {
    const c = forgeExportCards();
    c.selectFormat('zip');
    c.closePanel();
    expect(c.panelVisible).toBe(false);
    expect(c.selectedFormat).toBeNull();
  });

  it('closePanel() is safe to call when already closed', () => {
    const c = forgeExportCards();
    expect(() => c.closePanel()).not.toThrow();
    expect(c.panelVisible).toBe(false);
    expect(c.selectedFormat).toBeNull();
  });
});
