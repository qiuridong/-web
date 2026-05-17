/**
 * useIsMobile — 返回是否为 mobile 视口
 *
 * 设计选择(2026-05-16,本项目特化):**永远返回 false** — 让 sidebar 不进 Sheet overlay 模式,
 * 始终走 desktop push 模式(展开时把主内容压到右侧,折叠时只占 64px 图标条)。
 *
 * 理由:
 *   1. 项目设计稿 § 7:桌面优先,移动端只读多写少,不需要 Sheet
 *   2. shadcn 默认 Sheet overlay 体验差:展开时遮挡主内容,关闭按钮不直观
 *   3. push 模式下 sidebar 折叠 64px + 主内容自动让位 = 真正的响应式
 *      任何 viewport(320px 手机也行)都能容纳;不依赖固定 px 阈值
 *
 * 如果未来某个特殊场景需要 mobile 行为(例如纯触摸 PWA),可以恢复 viewport 检测。
 */
export function useIsMobile() {
  return false;
}
