/**
 * vite.config.js — StoryForge frontend build configuration
 *
 * Build output: web/dist/
 * Dev server: proxies /api requests to the FastAPI backend on port 7860
 *
 * NOTE: This build pipeline is optional. The app runs from CDN without it.
 *       Run `npm run build` to produce a production-optimised bundle.
 *
 * To add gzip/brotli compression, install vite-plugin-compression and uncomment:
 *   import viteCompression from 'vite-plugin-compression'
 *   ...plugins: [viteCompression({ algorithm: 'brotliCompress' })]
 */

import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  // Treat web/ as the project root so imports resolve from there
  root: 'web',

  build: {
    // Output to web/dist/ (gitignored, served by FastAPI's StaticFiles)
    outDir: 'dist',
    emptyOutDir: true,

    // Use esbuild minifier (default, fast) — swap to 'terser' for finer control
    minify: 'esbuild',

    // Only emit source maps in development; skip in production CI to reduce bundle size
    sourcemap: process.env.NODE_ENV !== 'production',

    // Warn when a chunk exceeds 500 kB (default is 500 kB; explicit here for visibility)
    chunkSizeWarningLimit: 500,

    rollupOptions: {
      // Entry point — the main SPA HTML file
      input: resolve(__dirname, 'web/index.html'),

      output: {
        /**
         * Manual chunk splitting — keeps vendor code in a separate cached chunk.
         *
         * Alpine.js is loaded from CDN in index.html, so it is not bundled here.
         * If Alpine is ever added as an npm dependency, add it to the 'alpine' chunk:
         *   if (id.includes('alpinejs')) return 'alpine'
         *
         * Current vendor chunks:
         *   vendor  — everything from node_modules not explicitly listed below
         */
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Split @tailwindcss/typography into its own chunk (large, rarely changes)
            if (id.includes('@tailwindcss')) return 'tailwind-vendor'
            // All other node_modules go into a single vendor chunk
            return 'vendor'
          }
        },

        // Deterministic chunk filenames with content hash for long-lived caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },

    // CSS code splitting — each async chunk gets its own CSS file
    cssCodeSplit: true,

    // Target modern browsers that support ES modules (reduces polyfill overhead)
    target: 'es2020',
  },

  css: {
    // PostCSS is configured via postcss.config.js (includes Tailwind + autoprefixer)
    // Tailwind purges unused classes automatically via the `content` paths in
    // tailwind.config.js — no extra config needed here.
    devSourcemap: true,
  },

  server: {
    port: 5173,
    proxy: {
      // Forward all /api/* requests to the FastAPI backend
      '/api': {
        target: 'http://localhost:7860',
        changeOrigin: true,
        rewrite: (path) => path, // keep /api prefix — FastAPI routes include it
      },
    },
  },

  preview: {
    port: 4173,
  },
})
