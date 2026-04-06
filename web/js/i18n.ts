/**
 * StoryForge — lightweight JSON-based i18n module for Alpine.js.
 *
 * Usage (Alpine store):
 *   Alpine.store('i18n', i18n);
 *
 * In templates:
 *   <span x-text="$store.i18n.t('key')"></span>
 */

type Locale = 'vi' | 'en';

interface I18nStore {
  locale: Locale;
  translations: Record<string, Record<string, string>>;
  t(key: string): string;
  setLocale(locale: Locale): void;
  loadTranslations(): Promise<void>;
}

const i18n: I18nStore = {
  locale: (
    typeof localStorage !== 'undefined'
      ? (localStorage.getItem('storyforge_locale') as Locale) || 'vi'
      : 'vi'
  ),
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

export default i18n;
