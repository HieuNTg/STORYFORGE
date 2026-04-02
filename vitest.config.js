/**
 * vitest.config.js — StoryForge frontend test configuration
 *
 * Runs Vitest with a jsdom environment to simulate a browser context for
 * Alpine.js component logic and fetch-based API client tests.
 *
 * Usage:
 *   npm test              — run all tests once
 *   npm run test:coverage — run tests + emit lcov / text coverage report
 *   npm run test:ui       — interactive Vitest UI (requires @vitest/ui)
 */

import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  test: {
    // jsdom gives us window, document, fetch stubs, and localStorage
    environment: 'jsdom',

    // Glob patterns for test files
    include: [
      'web/js/__tests__/**/*.test.js',
      'web/js/__tests__/**/*.spec.js',
    ],

    // Global test helpers (describe, it, expect, vi) without explicit imports
    globals: true,

    // Run setup file before each test suite — useful for Alpine.js initialisation
    setupFiles: ['web/js/__tests__/setup.js'],

    // Coverage configuration (used by `vitest --coverage`)
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      reportsDirectory: 'coverage',

      // Source files to measure coverage against
      include: ['web/js/**/*.js'],

      // Exclude test files and vendor/CDN shims from the report
      exclude: [
        'web/js/__tests__/**',
        'web/js/vendor/**',
      ],

      // Minimum coverage thresholds — CI fails if these are not met
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 60,
        statements: 60,
      },
    },

    // Resolves bare module names the same way Vite does during dev/build
    resolve: {
      alias: {
        '@': resolve(__dirname, 'web/js'),
      },
    },
  },
})
