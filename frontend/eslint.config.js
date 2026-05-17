/**
 * ESLint 9 flat config — React + TypeScript + react-hooks + react-refresh
 *
 * 设计契约:严格模式,错误而非警告;CI 跑 `pnpm lint` 必须 zero warnings。
 *
 * 全局 DOM/ES2022 通过 `globals` 包提供(browser env)。
 * `components/ui/*` 由 shadcn CLI 生成,我们不手改其代码风格;
 *   对该目录放宽 react-refresh / unused 规则。
 */
import js from '@eslint/js';
import globals from 'globals';
import tseslint from '@typescript-eslint/eslint-plugin';
import tsparser from '@typescript-eslint/parser';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  {
    ignores: [
      'dist',
      'node_modules',
      'coverage',
      '**/*.config.{js,mjs,ts}',
      'src/api/schema.d.ts',
      'src/vite-env.d.ts',
    ],
  },
  js.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parser: tsparser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
    },
  },
  {
    // shadcn copy-pasted UI primitives —— 由 CLI 生成,不强制本仓库的风格
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
      'no-undef': 'off',
    },
  },
  {
    // 路由表 / 入口文件天然导出非组件(loader / router 对象 / placeholder)
    files: ['src/app/router.tsx', 'src/main.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
];
