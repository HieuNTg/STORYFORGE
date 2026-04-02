/**
 * postcss.config.js — PostCSS plugin chain for StoryForge
 *
 * Plugins (order matters):
 *   1. tailwindcss — generates utility classes from scanned HTML/JS
 *   2. autoprefixer — adds vendor prefixes for cross-browser compatibility
 *
 * Consumed by Vite automatically during `npm run build` and `npm run dev`.
 */

module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
