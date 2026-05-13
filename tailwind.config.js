/**
 * tailwind.config.js — StoryForge Tailwind CSS configuration
 *
 * Scans web/**\/*.html and web/**\/*.js for class names.
 * Theme extensions mirror the design tokens defined in web/css/tokens.css
 * so Tailwind utility classes and CSS custom properties stay in sync.
 *
 * Plugin: @tailwindcss/typography — enables the `prose` class for story text.
 */

/** @type {import('tailwindcss').Config} */
module.exports = {
  // Class-based dark mode — the .dark class on <html> triggers dark: variants.
  // Toggled by the inline bootstrap script in index.html + Alpine store.
  darkMode: 'class',

  // Paths Tailwind scans to detect used class names for PurgeCSS/JIT tree-shaking.
  // Must cover every file that references Tailwind utilities — missing paths cause
  // classes to be purged in production builds.
  //
  // We scan TS sources only (not compiled .js siblings or web/dist/**) — minified
  // bundles add false-positive identifier matches that bloat the purged output.
  content: [
    'web/index.html',
    'web/dashboard.html',
    'web/js/**/*.ts',
    // Include any Jinja/HTML templates served by FastAPI (if present)
    'templates/**/*.html',
  ],

  theme: {
    extend: {
      // ── Brand colours (mirrors --sf-color-brand-* tokens) ──────────────
      colors: {
        brand: {
          50:  '#EFF6FF',
          100: '#DBEAFE',
          200: '#BFDBFE',
          500: '#3B82F6',
          600: '#2563EB',
          700: '#1D4ED8',
          800: '#1E40AF',
        },
        surface: {
          50:  '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
        },
        status: {
          success: '#16A34A',
          error:   '#DC2626',
          warning: '#F59E0B',
        },
      },

      // ── Font family (mirrors --sf-font-sans token) ──────────────────────
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },

      // ── Border radius (mirrors --sf-radius-* tokens) ────────────────────
      borderRadius: {
        sm:   '6px',
        md:   '8px',
        lg:   '12px',
        xl:   '16px',
        full: '9999px',
      },

      // ── Box shadow (mirrors --sf-shadow-* tokens) ───────────────────────
      boxShadow: {
        sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
      },

      // ── Transition duration (mirrors --sf-duration-* tokens) ─────────────
      transitionDuration: {
        fast: '150ms',
        base: '250ms',
        slow: '400ms',
      },
    },
  },

  plugins: [
    require('@tailwindcss/typography'),
  ],
}
