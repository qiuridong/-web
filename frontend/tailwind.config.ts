/**
 * Tailwind v4 配置文件
 *
 * v4 时代主要靠 src/app/index.css 中的 `@theme` directive 配置 token,
 * 这个文件**只放 plugin**(typography 等)。
 *
 * 设计稿契约:`进度/设计/前端UI设计.md` § 1.5、§ 11.1。
 *
 * shadcn CLI 在某些版本仍会读取此文件,故保留以满足 CLI 期望。
 */
import type { Config } from 'tailwindcss';
import typography from '@tailwindcss/typography';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  plugins: [typography],
} satisfies Config;
