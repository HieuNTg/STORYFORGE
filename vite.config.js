/**
 * vite.config.js — StoryForge frontend build configuration
 *
 * Build output: web/dist/
 * Dev server: proxies /api requests to the FastAPI backend on port 7860
 *
 * NOTE: This build pipeline is optional. The app runs from CDN without it.
 *       Run `npm run build` to produce a production-optimised bundle.
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

    rollupOptions: {
      // Entry point — the main SPA HTML file
      input: resolve(__dirname, 'web/index.html'),
    },

    // Produce source maps for easier debugging
    sourcemap: true,
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
