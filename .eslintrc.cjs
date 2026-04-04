// ESLint config for StoryForge frontend TypeScript sources
// Scope: web/js/**/*.ts  (run via `npm run lint`)
// eslint-config-prettier disables formatting rules that conflict with Prettier

/** @type {import('eslint').Linter.Config} */
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
    project: './tsconfig.json',
  },
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'prettier', // must be last — disables conflicting ESLint formatting rules
  ],
  env: {
    browser: true,
    es2020: true,
  },
  rules: {
    // Keep rules minimal (YAGNI) — add project-specific overrides here as needed
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
  ignorePatterns: ['dist/', 'node_modules/', '*.js', '*.cjs', '*.d.ts'],
}
