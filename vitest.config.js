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

    // Glob patterns for test files.
    // .ts only — tsc emits .js siblings for tests too; ignore those to
    // avoid double-counting.
    include: [
      'web/js/__tests__/**/*.test.ts',
      'web/js/__tests__/**/*.spec.ts',
      'web/js/**/__tests__/**/*.test.ts',
      'web/js/**/__tests__/**/*.spec.ts',
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

      // Source files to measure coverage against.
      // v8 coverage maps to .js runtime files (tsc output or native JS).
      // Exclude .ts files — they have 0 line coverage under v8 because
      // the runtime executes the compiled .js, not the .ts source.
      include: ['web/js/**/*.js'],

      // Exclude test files, type-only files, and vendor/CDN shims
      exclude: [
        'web/js/__tests__/**',
        'web/js/**/__tests__/**',
        'web/js/vendor/**',
        'web/js/types/**',
        'web/js/**/*.d.js',
      ],

      // Minimum coverage thresholds — CI fails if these are not met.
      // Lines/statements at 40% because legacy pages (library, pipeline,
      // gallery, providers, account, usage, branch-reader) have no unit
      // tests and are excluded from this sprint's scope. Forge components
      // and stores average 80-93% individually (see coverage report).
      // Branch/function thresholds reflect the well-tested forge surface.
      thresholds: {
        lines: 40,
        functions: 60,
        branches: 60,
        statements: 40,
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
