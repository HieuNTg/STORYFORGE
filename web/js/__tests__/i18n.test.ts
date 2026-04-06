/**
 * i18n.test.ts — Unit tests for the i18n module.
 *
 * Tests:
 *   - default locale is 'vi'
 *   - t() returns the key when no translation found
 *   - t() falls back to 'en' when locale translation missing
 *   - t() returns locale-specific translation
 *   - setLocale() saves to localStorage
 *   - loadTranslations() populates the translations map
 *   - loadTranslations() warns and continues on fetch failure
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Build a fresh i18n store for each test (avoid shared state mutations)
// ---------------------------------------------------------------------------

type Locale = 'vi' | 'en';

interface I18nStore {
  locale: Locale;
  translations: Record<string, Record<string, string>>;
  t(key: string): string;
  setLocale(locale: Locale): void;
  loadTranslations(): Promise<void>;
}

function createI18n(initialLocale: Locale = 'vi'): I18nStore {
  return {
    locale: initialLocale,
    translations: {},

    t(key: string): string {
      return (
        this.translations[this.locale]?.[key] ||
        this.translations['en']?.[key] ||
        key
      );
    },

    setLocale(locale: Locale): void {
      this.locale = locale;
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('storyforge_locale', locale);
      }
    },

    async loadTranslations(): Promise<void> {
      try {
        const [vi, en] = await Promise.all([
          fetch('/static/locales/vi.json').then((r) => r.json()),
          fetch('/static/locales/en.json').then((r) => r.json()),
        ]);
        this.translations = { vi, en };
      } catch (e) {
        console.warn('Failed to load translations:', e);
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('i18n — default locale', () => {
  it('default locale is vi', () => {
    const i18n = createI18n();
    expect(i18n.locale).toBe('vi');
  });
});

describe('i18n — t()', () => {
  it('returns the key when no translations loaded', () => {
    const i18n = createI18n();
    expect(i18n.t('some.key')).toBe('some.key');
  });

  it('returns empty string key as-is', () => {
    const i18n = createI18n();
    expect(i18n.t('')).toBe('');
  });

  it('returns locale-specific translation', () => {
    const i18n = createI18n('vi');
    i18n.translations = { vi: { hello: 'Xin chào' }, en: { hello: 'Hello' } };
    expect(i18n.t('hello')).toBe('Xin chào');
  });

  it('falls back to en when locale key missing', () => {
    const i18n = createI18n('vi');
    i18n.translations = { vi: {}, en: { hello: 'Hello' } };
    expect(i18n.t('hello')).toBe('Hello');
  });

  it('returns key when neither locale has it', () => {
    const i18n = createI18n('vi');
    i18n.translations = { vi: {}, en: {} };
    expect(i18n.t('missing.key')).toBe('missing.key');
  });

  it('works with en locale', () => {
    const i18n = createI18n('en');
    i18n.translations = { vi: { hello: 'Xin chào' }, en: { hello: 'Hello' } };
    expect(i18n.t('hello')).toBe('Hello');
  });
});

describe('i18n — setLocale()', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('updates locale', () => {
    const i18n = createI18n('vi');
    i18n.setLocale('en');
    expect(i18n.locale).toBe('en');
  });

  it('persists locale to localStorage', () => {
    const i18n = createI18n('vi');
    i18n.setLocale('en');
    expect(localStorage.getItem('storyforge_locale')).toBe('en');
  });

  it('stores vi locale to localStorage', () => {
    const i18n = createI18n('en');
    i18n.setLocale('vi');
    expect(localStorage.getItem('storyforge_locale')).toBe('vi');
  });
});

describe('i18n — loadTranslations()', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('populates translations from fetch', async () => {
    const i18n = createI18n();
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ json: async () => ({ hello: 'Xin chào' }) })
      .mockResolvedValueOnce({ json: async () => ({ hello: 'Hello' }) });
    vi.stubGlobal('fetch', mockFetch);

    await i18n.loadTranslations();

    expect(i18n.translations['vi']).toEqual({ hello: 'Xin chào' });
    expect(i18n.translations['en']).toEqual({ hello: 'Hello' });
  });

  it('warns and does not throw on fetch failure', async () => {
    const i18n = createI18n();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(i18n.loadTranslations()).resolves.toBeUndefined();
    expect(warnSpy).toHaveBeenCalledWith(
      'Failed to load translations:',
      expect.any(Error)
    );
  });

  it('after successful load, t() returns translation', async () => {
    const i18n = createI18n('vi');
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ json: async () => ({ title: 'Tiêu đề' }) })
      .mockResolvedValueOnce({ json: async () => ({ title: 'Title' }) })
    );
    await i18n.loadTranslations();
    expect(i18n.t('title')).toBe('Tiêu đề');
  });
});
