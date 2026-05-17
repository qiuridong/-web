/**
 * PostCSS 配置 — Tailwind v4 通过 @tailwindcss/postcss 插件接入。
 *
 * 设计稿契约:`进度/设计/前端UI设计.md` § 1.5。
 * Tailwind v4 不需要也不使用 vite 插件;@theme directive 写在 src/app/index.css 里。
 */
export default {
  plugins: {
    '@tailwindcss/postcss': {},
    autoprefixer: {},
  },
};
