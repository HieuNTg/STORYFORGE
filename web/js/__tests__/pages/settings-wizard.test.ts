/**
 * pages/settings-wizard.test.ts
 *
 * Unit tests for forgeSettingsWizard() Alpine.data factory.
 *
 * Covers:
 *   - Default state shape
 *   - shouldShow: dismissed flag in localStorage → false
 *   - shouldShow: no API key + no dismissed flag → true
 *   - shouldShow: API key present → false
 *   - shouldShow: localStorage unavailable (throws) → false
 *   - next(): step 1 -> 2 -> 3, stays at 3
 *   - dismiss(): sets localStorage flag, show = false
 *   - dismiss(): silent no-op when localStorage throws
 *   - finish(): calls dismiss() (show = false, flag set)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { forgeSettingsWizard } from '../../pages/settings';

describe('forgeSettingsWizard', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(Alpine.store).mockReturnValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns correct default state', () => {
    const w = forgeSettingsWizard();
    expect(w.show).toBe(false);
    expect(w.step).toBe(1);
    expect(w.selectedProvider).toBe('openai');
    expect(w.apiKey).toBe('');
    expect(w.selectedGenre).toBe('fantasy');
    expect(w.genres).toHaveLength(5);
  });

  it('shouldShow: returns false when dismissed flag is set', () => {
    localStorage.setItem('sf:settings-wizard-dismissed', '1');
    const w = forgeSettingsWizard();
    expect(w.shouldShow()).toBe(false);
  });

  it('shouldShow: returns true when no key + no dismissed flag', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({ config: { llm: { api_key: '' } } }));
    const w = forgeSettingsWizard();
    expect(w.shouldShow()).toBe(true);
  });

  it('shouldShow: returns false when API key is configured', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({
      config: { llm: { api_key: 'sk-real-key-abc' } },
    }));
    const w = forgeSettingsWizard();
    expect(w.shouldShow()).toBe(false);
  });

  it('shouldShow: returns false when Alpine.store throws', () => {
    vi.mocked(Alpine.store).mockImplementation(() => { throw new Error('no store'); });
    const w = forgeSettingsWizard();
    expect(w.shouldShow()).toBe(false);
  });

  it('next() advances step from 1 to 2', () => {
    const w = forgeSettingsWizard();
    w.next();
    expect(w.step).toBe(2);
  });

  it('next() advances step from 2 to 3', () => {
    const w = forgeSettingsWizard();
    w.next();
    w.next();
    expect(w.step).toBe(3);
  });

  it('next() does not advance past step 3', () => {
    const w = forgeSettingsWizard();
    w.next(); w.next(); w.next();
    expect(w.step).toBe(3);
  });

  it('dismiss() sets localStorage flag and show = false', () => {
    const w = forgeSettingsWizard();
    w.show = true;
    w.dismiss();
    expect(w.show).toBe(false);
    expect(localStorage.getItem('sf:settings-wizard-dismissed')).toBe('1');
  });

  it('dismiss() is a silent no-op when localStorage throws', () => {
    const getItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage quota');
    });
    const w = forgeSettingsWizard();
    w.show = true;
    expect(() => w.dismiss()).not.toThrow();
    expect(w.show).toBe(false);
    getItem.mockRestore();
  });

  it('finish() calls dismiss (show = false, flag set)', async () => {
    vi.mocked(Alpine.store).mockImplementation(() => null);
    const w = forgeSettingsWizard();
    w.show = true;
    await w.finish();
    expect(w.show).toBe(false);
    expect(localStorage.getItem('sf:settings-wizard-dismissed')).toBe('1');
  });

  it('finish() is silent when store.save throws', async () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({
      config: { llm: {} },
      save: async () => { throw new Error('save failed'); },
    }));
    const w = forgeSettingsWizard();
    w.show = true;
    await expect(w.finish()).resolves.not.toThrow();
    expect(w.show).toBe(false);
  });
});
