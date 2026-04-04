/**
 * vite.config.js — StoryForge frontend build configuration
 *
 * Build output: web/dist/
 * Dev server: proxies /api requests to the FastAPI backend on port 7860
 *
 * NOTE: This build pipeline is optional. The app runs from CDN without it.
 *       Run `npm run build` to produce a production-optimised bundle.
 *
 * Compression: gzip + brotli via vite-plugin-compression (both enabled below).
 */

import { defineConfig } from 'vite'
import { resolve } from 'path'
import viteCompression from 'vite-plugin-compression'

// TypeScript files are supported natively by Vite/esbuild — no extra plugin needed.
// This config adds explicit .ts extension resolution so bare imports like
// `import API from '@/api-client'` resolve to api-client.ts before api-client.js.

export default defineConfig({
  plugins: [
    // Emit .gz companion files alongside every asset > 10 kB
    viteCompression({ algorithm: 'gzip', threshold: 10240 }),
    // Emit .br companion files (brotli gives ~20% better ratio than gzip)
    viteCompression({ algorithm: 'brotliCompress', ext: '.br', threshold: 10240 }),
  ],

  // Treat web/ as the project root so imports resolve from there
  root: 'web',

  resolve: {
    // Prefer .ts over .js when both exist (enables incremental migration)
    extensions: ['.ts', '.js', '.json'],
    alias: {
      '@': resolve(__dirname, 'web/js'),
    },
  },

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
            if (id.includes('@tailwindcss')) return 'tailwind-vendor'
            return 'vendor'
          }
          // Page-level code splitting — each page gets its own cached chunk
          if (id.includes('/web/js/pages/')) {
            const match = id.match(/pages\/(\w+)/)
            if (match) return 'page-' + match[1]
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
