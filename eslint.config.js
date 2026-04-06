// ESLint flat config for StoryForge frontend TypeScript sources
// Scope: web/js/**/*.ts  (run via `npm run lint`)
// Replaces .eslintrc.cjs — ESLint 10 dropped legacy .eslintrc format

import tseslint from '@typescript-eslint/eslint-plugin';
import tsparser from '@typescript-eslint/parser';
import prettierConfig from 'eslint-config-prettier';

export default [
  {
    files: ['web/js/**/*.ts'],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        project: './tsconfig.json',
      },
      globals: {
        // browser globals (replaces env: { browser: true, es2020: true })
        window: 'readonly',
        document: 'readonly',
        Alpine: 'readonly',
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      // Keep rules minimal (YAGNI) — add project-specific overrides here as needed
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  prettierConfig,
];
