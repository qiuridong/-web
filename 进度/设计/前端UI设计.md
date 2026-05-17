# 签到脚本聚合管理面板 — 前端 UI/UX 设计文档 v2.0(React 版)

> 本文档为编码 Agent 的设计契约。技术栈已锁定:**React 18 + Vite + TypeScript + React Router 7 + Zustand + TanStack Query 5 + shadcn/ui + Tailwind v4**。后端 FastAPI + REST + SSE。
>
> 设计目标:做一个克制、现代、有温度的后台工具。参考调性 **Linear / Vercel / Raycast / cal.com / shadcn examples**。
>
> 相对于 v1.0(Vue + Element Plus 版),本版的核心切换:
>
> - 框架 Vue 3 → React 18
> - 路由 Vue Router → React Router 7(`loader` + `redirect` 鉴权)
> - 状态 Pinia → Zustand(全局)+ TanStack Query 5(服务端)
> - UI 基底 Element Plus → shadcn/ui(Radix UI + Tailwind v4)
> - 表单 el-form → react-hook-form + zod
> - 图表 ECharts → Recharts(主)+ 借鉴 Tremor
> - 命令面板 自研 → cmdk
> - Toast → sonner
> - 主题切换 → next-themes
> - 终端日志 → @xterm/xterm
> - 动画 → Framer Motion 12
>
> v1.0 中的视觉风格 token(色板、字号、间距、阴影、动画 token、调性)在本版中**升级为 OKLCH 表示并适配 shadcn/ui CSS variables 规范**,设计语言一脉相承。

---

## 目录

```
1.  视觉风格指南
2.  路由表
3.  关键页面 wireframe
4.  公共组件清单
5.  状态管理
6.  API 封装层
7.  响应式策略
8.  美化关键手法(精炼到组件级)
9.  推荐目录结构
10. 关键依赖
11. shadcn/ui 安装与用法约定
```

---

## 1. 视觉风格指南

### 1.1 设计调性

定调五个形容词:**克制、现代、精致、安静、可信赖**。这是后台工具,不是消费 SaaS 着陆页,所有装饰必须服务于"让人 7×24 看着也不累、不焦虑、不出错"。

#### 1.1.1 克制(Restrained)

这是给个人/小团队长期挂着看的工具,不能花哨。所有装饰都必须服务于信息层级——**禁止纯装饰渐变、禁止无意义图形、禁止过度动画**。颜色只在"需要被注意"的位置出现:状态徽标、CTA 按钮、当前选中项、活动指示点。其余地方使用大量中性灰阶和留白。`muted-foreground` 是次要文字的唯一颜色,`muted` 是次要背景的唯一颜色,不允许自创灰阶。CTA 全页面只允许 1 个 primary 按钮——若有多个动作,只有最关键的一个用 default variant,其余用 outline 或 ghost。

#### 1.1.2 现代(Modern)

抛弃 2010 年代企业后台那种"白底 + 灰线 + 彩色填充按钮 + 灰扁平表格"的糟糕组合。我们走 2025-2026 的当代审美:**大圆角(0.625rem / 10px 起,卡片 14px)、半透明分层(border 用 oklch + alpha)、柔和阴影、精致字体(Inter Variable)、Tabular Numbers、深色模式作为一等公民**。所有边框统一用 `border-border`(也就是 `oklch(... / 0.08)` 级别的低对比度边框),禁止 `border-2` 以上的粗实线。卡片之间用间距而非分隔线。

#### 1.1.3 精致(Refined)

每个微交互单独看微不足道,叠在一起就是"高级感"的来源:

- 按钮 hover 颜色过渡 180ms + `active:scale-[0.98]` 按压感
- 开关切换 spring easing(framer-motion 默认 stiffness 200 / damping 25)
- 数字变化 count-up 动效(react-countup 或 framer-motion `useSpring`)
- 状态点带"呼吸"光晕(scale 1 ↔ 1.4 + opacity 0 ↔ 0.6,2s 循环)
- 切换 Tab 用 `<AnimatePresence mode="wait">` 做 fade-slide(opacity + x: 8 → 0)
- 卡片 hover `-translate-y-0.5 + shadow-md`
- 路由切换 fade-slide,但 timing 控制在 160ms 以内,不能慢
- 表格行 hover 整行 `bg-muted/40`,鼠标移开 120ms 内淡出
- focus 全部用 `focus-visible:ring-2 ring-ring ring-offset-2`,**不允许任何元素出现默认浏览器 outline**

#### 1.1.4 安静(Quiet)

这个工具会被长时间盯着看。配色饱和度普遍较低(`chroma` 不超过 0.18),文字与背景对比度精确控制(WCAG AA,正文 contrast 7+,次要文字 4.5+,但**不能过头到刺眼**);loading 用 skeleton 而非 spinner;toast 默认右上角滑入,**不发声、不闪烁、不振铃**;深色模式不使用纯黑 `#000`,而是 `oklch(0.16 0.012 252)` 这种偏蓝的 near-black,搭配 `oklch(0.95 0.005 252)` 的 near-white 文字,长时间观看不疲劳。

#### 1.1.5 可信赖(Trustworthy)

这是个会自动跑脚本、发通知、管密钥的工具。视觉必须传达"它不会坏、不会乱来"的稳重感。具体手段:

- 统一的间距栅格(0.25rem / 4px 为 base unit)
- 严格的字号体系(只有 8 档,不许临时新增)
- 明确的状态语义色(success / warning / danger / info 四色固定,定义在 CSS vars,只能用 `text-success` `bg-warning` 等)
- 重大操作必弹 `<AlertDialog>` 二次确认(删除、立即执行、清空备份等)
- 加密相关的操作(secret 字段、备份导出)必有 `<Alert variant="warning">` 提示"主密钥丢失=所有配置作废,请妥善保管"
- 时间一律 ISO + 相对显示(`刚刚 / 3 分钟前 / 2 小时前 / 2026-05-12 08:32`),tooltip 显示绝对时间

---

### 1.2 配色方案(shadcn 标准 CSS vars + OKLCH)

> 采用 **shadcn/ui Tailwind v4 风格**:CSS variables 定义在 `:root` 与 `.dark`,Tailwind 4 通过 `@theme inline` 把变量映射成 utility class。颜色全部用 **OKLCH** 表示,这是 2026 主流方案,色相、亮度、彩度互相独立可控,深色模式调整更精准。

#### 1.2.1 完整 `:root`(浅色模式)

```css
:root {
  /* ===== 基础语义色(shadcn 标准 12 token) ===== */
  --background: oklch(1 0 0);                       /* 纯白底 */
  --foreground: oklch(0.18 0.018 252);              /* 主文字,微蓝中性 */

  --card: oklch(1 0 0);                              /* 卡片底,= background */
  --card-foreground: oklch(0.18 0.018 252);

  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.18 0.018 252);

  /* ===== 主色 Brand:Indigo 系,基准 oklch(0.58 0.18 268) ≈ #5865F2 ===== */
  --primary: oklch(0.58 0.18 268);                  /* 主按钮、链接、focus ring */
  --primary-foreground: oklch(0.98 0.003 268);

  /* ===== 次要 ===== */
  --secondary: oklch(0.965 0.005 252);              /* 次按钮底 / hover 浅底 */
  --secondary-foreground: oklch(0.20 0.018 252);

  --muted: oklch(0.965 0.005 252);                  /* 次背景 */
  --muted-foreground: oklch(0.48 0.012 252);        /* 次文字 */

  --accent: oklch(0.965 0.005 252);                 /* 选中底 */
  --accent-foreground: oklch(0.20 0.018 252);

  /* ===== 强调色 Teal,用于次要 CTA、统计图差异色 ===== */
  --accent-2: oklch(0.69 0.13 188);                  /* ≈ #14B8A6 Teal-500 */
  --accent-2-foreground: oklch(0.98 0.003 188);

  /* ===== 语义色(全部用 OKLCH,统一彩度) ===== */
  --success: oklch(0.69 0.16 152);                  /* Emerald-500 ≈ #10B981 */
  --success-foreground: oklch(0.98 0.005 152);
  --warning: oklch(0.78 0.16 75);                   /* Amber-500 ≈ #F59E0B */
  --warning-foreground: oklch(0.18 0.04 75);
  --danger: oklch(0.65 0.20 17);                    /* Rose-500 ≈ #F43F5E */
  --danger-foreground: oklch(0.98 0.005 17);
  --info: oklch(0.69 0.15 230);                     /* Sky-500 ≈ #0EA5E9 */
  --info-foreground: oklch(0.98 0.005 230);

  /* shadcn 'destructive' 别名 = danger,保持向下兼容 */
  --destructive: var(--danger);
  --destructive-foreground: var(--danger-foreground);

  /* ===== 边框 / 输入框 / focus ring ===== */
  --border: oklch(0.92 0.005 252);                  /* 极淡边框 */
  --input: oklch(0.92 0.005 252);
  --ring: oklch(0.58 0.18 268 / 0.5);               /* 主色半透明 ring */

  /* ===== Recharts / 数据可视化 5 色调色板 ===== */
  --chart-1: oklch(0.58 0.18 268);                  /* indigo,= primary */
  --chart-2: oklch(0.69 0.13 188);                  /* teal */
  --chart-3: oklch(0.78 0.16 75);                   /* amber */
  --chart-4: oklch(0.69 0.16 152);                  /* emerald */
  --chart-5: oklch(0.65 0.20 17);                   /* rose */

  /* ===== Sidebar(shadcn sidebar block 专用) ===== */
  --sidebar: oklch(0.985 0.003 252);                /* 比 background 稍灰 */
  --sidebar-foreground: oklch(0.20 0.018 252);
  --sidebar-primary: oklch(0.58 0.18 268);
  --sidebar-primary-foreground: oklch(0.98 0.003 268);
  --sidebar-accent: oklch(0.94 0.008 252);
  --sidebar-accent-foreground: oklch(0.20 0.018 252);
  --sidebar-border: oklch(0.92 0.005 252);
  --sidebar-ring: oklch(0.58 0.18 268 / 0.5);

  /* ===== 圆角(shadcn 标准) ===== */
  --radius: 0.625rem;                               /* 10px,作为 base */
  /* card/popover/dialog 用更大 radius:0.875rem = 14px */
  /* button/input/badge 用 base radius */

  /* ===== 阴影 ===== */
  --shadow-xs: 0 1px 2px 0 oklch(0 0 0 / 0.04);
  --shadow-sm: 0 1px 3px 0 oklch(0 0 0 / 0.05), 0 1px 2px -1px oklch(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px oklch(0 0 0 / 0.06), 0 2px 4px -2px oklch(0 0 0 / 0.06);
  --shadow-lg: 0 10px 15px -3px oklch(0 0 0 / 0.06), 0 4px 6px -4px oklch(0 0 0 / 0.04);
  --shadow-xl: 0 20px 25px -5px oklch(0 0 0 / 0.08), 0 8px 10px -6px oklch(0 0 0 / 0.05);

  /* ===== 动画 timing token ===== */
  --ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast: 120ms;
  --duration-base: 180ms;
  --duration-slow: 280ms;
}
```

#### 1.2.2 `.dark`(深色模式,重新调色而非简单反色)

```css
.dark {
  /* ===== 基础:near-black 而非纯黑;偏蓝中性 ===== */
  --background: oklch(0.16 0.012 252);              /* #0D1117 类灰蓝黑 */
  --foreground: oklch(0.95 0.005 252);              /* near-white,微暖 */

  --card: oklch(0.20 0.012 252);                     /* 比 background 高一档,有"浮起"感 */
  --card-foreground: oklch(0.95 0.005 252);

  --popover: oklch(0.22 0.012 252);
  --popover-foreground: oklch(0.95 0.005 252);

  /* 主色亮度抬升 + 彩度略降,避免过艳;白文 contrast 通过 */
  --primary: oklch(0.69 0.16 268);                   /* 比浅色亮一档,看着更"亮但不刺" */
  --primary-foreground: oklch(0.16 0.012 268);

  --secondary: oklch(0.26 0.010 252);
  --secondary-foreground: oklch(0.95 0.005 252);

  --muted: oklch(0.24 0.010 252);
  --muted-foreground: oklch(0.68 0.012 252);

  --accent: oklch(0.28 0.012 252);
  --accent-foreground: oklch(0.95 0.005 252);

  --accent-2: oklch(0.74 0.12 188);

  /* 语义色:深色下亮度普遍 +0.05,彩度 -0.02 */
  --success: oklch(0.74 0.14 152);
  --success-foreground: oklch(0.18 0.04 152);
  --warning: oklch(0.82 0.14 75);
  --warning-foreground: oklch(0.18 0.04 75);
  --danger: oklch(0.70 0.18 17);
  --danger-foreground: oklch(0.98 0.005 17);
  --info: oklch(0.74 0.13 230);
  --info-foreground: oklch(0.18 0.04 230);
  --destructive: var(--danger);
  --destructive-foreground: var(--danger-foreground);

  --border: oklch(1 0 0 / 0.10);                    /* 半透明白边,深色下显得"漂浮" */
  --input: oklch(1 0 0 / 0.10);
  --ring: oklch(0.69 0.16 268 / 0.55);

  /* 图表深色调整:增加饱和让在暗底辨识更高 */
  --chart-1: oklch(0.69 0.16 268);
  --chart-2: oklch(0.74 0.12 188);
  --chart-3: oklch(0.82 0.14 75);
  --chart-4: oklch(0.74 0.14 152);
  --chart-5: oklch(0.70 0.18 17);

  /* Sidebar 深色:比 background 再深一档,与右侧主区做层次 */
  --sidebar: oklch(0.14 0.012 252);
  --sidebar-foreground: oklch(0.92 0.005 252);
  --sidebar-primary: oklch(0.69 0.16 268);
  --sidebar-primary-foreground: oklch(0.16 0.012 252);
  --sidebar-accent: oklch(0.22 0.012 252);
  --sidebar-accent-foreground: oklch(0.95 0.005 252);
  --sidebar-border: oklch(1 0 0 / 0.08);
  --sidebar-ring: oklch(0.69 0.16 268 / 0.55);

  /* 深色阴影:用更大模糊 + 内嵌高光线模拟"边缘抓光" */
  --shadow-xs: 0 1px 2px 0 oklch(0 0 0 / 0.30), inset 0 1px 0 0 oklch(1 0 0 / 0.04);
  --shadow-sm: 0 1px 3px 0 oklch(0 0 0 / 0.35), 0 1px 2px -1px oklch(0 0 0 / 0.30), inset 0 1px 0 0 oklch(1 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px oklch(0 0 0 / 0.40), 0 2px 4px -2px oklch(0 0 0 / 0.35), inset 0 1px 0 0 oklch(1 0 0 / 0.06);
  --shadow-lg: 0 10px 15px -3px oklch(0 0 0 / 0.45), 0 4px 6px -4px oklch(0 0 0 / 0.35), inset 0 1px 0 0 oklch(1 0 0 / 0.06);
  --shadow-xl: 0 20px 25px -5px oklch(0 0 0 / 0.50), 0 8px 10px -6px oklch(0 0 0 / 0.40), inset 0 1px 0 0 oklch(1 0 0 / 0.08);
}
```

> 关键点:深色 `--card` 比 `--background` 略亮一档,加上 `inset 0 1px 0 oklch(1 0 0 / 0.06)` 模拟"边缘抓光",卡片有立体浮起感而不是平贴底色——这是 Linear / cal.com 深色模式的关键手法之一。

---

### 1.3 字体(完整 font-family 字符串)

```css
--font-sans:
  'Inter Variable',
  -apple-system,
  BlinkMacSystemFont,
  'PingFang SC',
  'HarmonyOS Sans SC',
  'Microsoft YaHei',
  'Helvetica Neue',
  Arial,
  'Noto Sans CJK SC',
  sans-serif,
  'Apple Color Emoji',
  'Segoe UI Emoji';

--font-mono:
  'JetBrains Mono Variable',
  'JetBrains Mono',
  'Fira Code',
  'SF Mono',
  Consolas,
  'Liberation Mono',
  Menlo,
  monospace;
```

**特性启用**(全局 `body`):

```css
body {
  font-family: var(--font-sans);
  font-feature-settings: 'cv11', 'ss01', 'ss03', 'salt';  /* Inter 单层 a/g、矩形 i 点等高级特性 */
  font-optical-sizing: auto;
  font-variation-settings: 'opsz' 16;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}
```

**字重梯度**:Regular 400 / Medium 500 / Semibold 600 / Bold 700。**不使用 300 / 800 / 900**(在中文 fallback 上变形严重)。

**中文字体策略**:
- macOS 用 PingFang SC(系统自带,无需加载)
- HarmonyOS 设备用 HarmonyOS Sans SC(系统自带)
- Windows 用 Microsoft YaHei(系统自带)兜底
- 国际访问用 Noto Sans CJK SC fallback
- **不打包中文字体**(单字重 6MB+ 太重,首屏体验差)

**自托管 Inter**:用 `@fontsource-variable/inter`,在 `main.tsx` 顶部 `import '@fontsource-variable/inter'`,**不走 Google Fonts CDN**(国内访问慢 + 隐私)。同理 JetBrains Mono 用 `@fontsource-variable/jetbrains-mono`。

---

### 1.4 字号 / 间距 / 圆角 / 阴影 / 动画 token

#### 1.4.1 字号(只允许 8 档,不许临时新增)

| Tailwind class | size | line-height | letter-spacing | 用途 |
|---|---|---|---|---|
| `text-xs` | 0.75rem (12) | 1rem (16) | 0.01em | 标签、辅助说明 |
| `text-sm` | 0.875rem (14) | 1.25rem (20) | 0 | 表格 body、表单 label、次要文字 |
| `text-base` | 1rem (16) | 1.5rem (24) | -0.005em | **正文默认** |
| `text-lg` | 1.125rem (18) | 1.75rem (28) | -0.01em | 卡片标题 |
| `text-xl` | 1.25rem (20) | 1.75rem (28) | -0.015em | section heading |
| `text-2xl` | 1.5rem (24) | 2rem (32) | -0.02em | 页面 H1 |
| `text-3xl` | 1.875rem (30) | 2.25rem (36) | -0.025em | 仪表盘 KPI 数字 |
| `text-4xl` | 2.25rem (36) | 2.5rem (40) | -0.03em | 登录页主标题 |

**关键负字距(negative tracking)**:仅大于等于 18px 的字号才用负 letter-spacing,这是 Inter / GeistSans 风格的"现代感"来源,小字号(< 16)绝对不能用,会让中文挤在一起。

#### 1.4.2 间距(4px base,Tailwind 默认 spacing scale 即可)

设计原则:**只用 4 的倍数**。常用值 `1 / 1.5 / 2 / 3 / 4 / 6 / 8 / 10 / 12 / 16`(对应 4 / 6 / 8 / 12 / 16 / 24 / 32 / 40 / 48 / 64 px)。

- **卡片内 padding**:`p-6`(24px),`p-5`(20px,紧凑型)
- **卡片之间 gap**:`gap-4`(16px),`gap-6`(24px,主区)
- **表单字段之间**:`space-y-4`(16px)
- **section 之间**:`space-y-8` (32px) 到 `space-y-12` (48px)
- **页面主区 padding**:`px-8 py-6`(桌面)/ `px-6 py-5`(紧凑)
- **侧栏 padding**:`px-3 py-4`

#### 1.4.3 圆角

| token | 值 | 用途 |
|---|---|---|
| `rounded-sm` | 4px | 小标签、tooltip |
| `rounded-md` | 6px | input、select、small button |
| `rounded-lg` | 10px (`--radius`) | **默认 button、avatar、icon-bg** |
| `rounded-xl` | 14px | **card、dialog、popover** |
| `rounded-2xl` | 18px | 仪表盘大卡片、登录卡 |
| `rounded-full` | 9999px | dot、avatar 圆头、pill badge |

> shadcn/ui 内部组件已经按 `--radius` 计算:`rounded-md` = `calc(var(--radius) - 4px)`,`rounded-lg` = `calc(var(--radius) - 2px)`,`rounded-xl` = `calc(var(--radius) + 4px)`。这是 shadcn 的精妙之处:改一个 `--radius` 即可一致缩放所有圆角。

#### 1.4.4 阴影

**浅色**:见 §1.2.1 的 5 档 `--shadow-*`,常用 `shadow-xs`(hover 卡)、`shadow-sm`(普通卡)、`shadow-md`(强调卡 / dropdown)、`shadow-lg`(dialog)、`shadow-xl`(popover、command palette)。

**深色额外**:每档都包含 `inset 0 1px 0 oklch(1 0 0 / 0.06)`,模拟边缘抓光。这是深色模式不显"扁平死黑"的关键。

**应用规则**:
- 卡片默认 `shadow-xs`,hover `shadow-md`
- dropdown / popover 用 `shadow-md`
- dialog 用 `shadow-xl`
- toast 用 `shadow-lg`

#### 1.4.5 动画 token

| token | 值 | 用途 |
|---|---|---|
| `--duration-fast` | 120ms | hover 颜色变化、focus ring 出现 |
| `--duration-base` | 180ms | 按钮按下回弹、tab 切换 |
| `--duration-slow` | 280ms | 路由切换、dialog 进入 |
| `--ease-out-quart` | `cubic-bezier(0.25, 1, 0.5, 1)` | 默认进入动画 |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | spring 弹性回弹(开关、按压释放) |

**framer-motion 默认 transition**:`{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }`(对齐 base + ease-out-quart)。

---

### 1.5 Tailwind v4 `@theme` directive 完整 `index.css` 骨架

```css
/* src/app/index.css */
@import 'tailwindcss';

/* tw-animate-css 提供 shadcn 默认 animation utility(fade-in / accordion-up 等) */
@import 'tw-animate-css';

/* 强制启用 .dark class 模式(默认 @media,我们要 next-themes 手动切) */
@custom-variant dark (&:is(.dark *));

/* ============ CSS variables(放最前) ============ */
:root {
  /* …… 见 §1.2.1 完整定义 …… */
}

.dark {
  /* …… 见 §1.2.2 完整定义 …… */
}

/* ============ Tailwind v4 @theme:把 CSS vars 暴露成 utility ============ */
@theme inline {
  /* color tokens */
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-danger: var(--danger);
  --color-danger-foreground: var(--danger-foreground);
  --color-info: var(--info);
  --color-info-foreground: var(--info-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);

  /* radius scale,基于 --radius 自动衍生(shadcn 约定) */
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  --radius-2xl: calc(var(--radius) + 8px);

  /* font families */
  --font-sans: 'Inter Variable', -apple-system, BlinkMacSystemFont,
               'PingFang SC', 'HarmonyOS Sans SC', 'Microsoft YaHei',
               'Helvetica Neue', Arial, 'Noto Sans CJK SC', sans-serif,
               'Apple Color Emoji', 'Segoe UI Emoji';
  --font-mono: 'JetBrains Mono Variable', 'JetBrains Mono', 'Fira Code',
               'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;

  /* 自定义关键帧:呼吸点 + mesh 漂移 */
  --animate-pulse-dot: pulseDot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  --animate-mesh-drift: meshDrift 40s ease-in-out infinite alternate;
  --animate-shimmer: shimmer 1.6s linear infinite;

  @keyframes pulseDot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50%      { transform: scale(1.4); opacity: 0.55; }
  }
  @keyframes meshDrift {
    0%   { transform: translate3d(-3%, -2%, 0) scale(1.02); }
    50%  { transform: translate3d(3%, 1%, 0) scale(1.06); }
    100% { transform: translate3d(-2%, 3%, 0) scale(1.02); }
  }
  @keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
}

/* ============ 基础 layer ============ */
@layer base {
  * {
    @apply border-border;
  }

  html {
    @apply antialiased;
    text-rendering: optimizeLegibility;
    /* 滚动条不抢空间 */
    scrollbar-gutter: stable;
  }

  body {
    @apply bg-background text-foreground font-sans;
    font-feature-settings: 'cv11', 'ss01', 'ss03', 'salt';
    font-optical-sizing: auto;
  }

  /* 焦点环统一 */
  *:focus-visible {
    @apply outline-none ring-2 ring-ring ring-offset-2 ring-offset-background;
  }

  /* 内置滚动条美化(macOS 风) */
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb {
    @apply bg-border rounded-full;
  }
  ::-webkit-scrollbar-thumb:hover {
    @apply bg-muted-foreground/30;
  }
  ::-webkit-scrollbar-track { background: transparent; }

  /* 全局选中色 */
  ::selection {
    background-color: oklch(0.58 0.18 268 / 0.25);
  }

  .tabular-nums {
    font-variant-numeric: tabular-nums;
  }
}

/* ============ utility 层:小工具 ============ */
@layer utilities {
  /* 卡片 hover 浮起 */
  .card-hover {
    @apply transition-all duration-180 ease-[cubic-bezier(0.25,1,0.5,1)]
           hover:-translate-y-0.5 hover:shadow-md;
  }

  /* 按钮按压感 */
  .btn-press {
    @apply transition-transform active:scale-[0.98];
  }

  /* 玻璃拟态卡(登录页) */
  .glass {
    background-color: oklch(1 0 0 / 0.7);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
  }
  .dark .glass {
    background-color: oklch(0.20 0.012 252 / 0.6);
  }

  /* 状态点呼吸光晕 */
  .dot-pulse::before {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: 9999px;
    background: currentColor;
    opacity: 0.45;
    animation: var(--animate-pulse-dot);
    z-index: -1;
  }

  /* skeleton shimmer */
  .skeleton-shimmer {
    background: linear-gradient(
      90deg,
      var(--muted) 0%,
      color-mix(in oklch, var(--muted) 80%, var(--foreground) 20%) 50%,
      var(--muted) 100%
    );
    background-size: 200% 100%;
    animation: var(--animate-shimmer);
  }
}
```

> 关键:`@theme inline` 把 CSS variables 提升为 Tailwind 4 的 color/spacing token,这样 `bg-primary` `text-foreground` `border-border` `text-success` 全部可用。所有自定义色都按这个模式注册,**不要再手写 `bg-[oklch(...)]`**。

---

## 2. 路由表

### 2.1 路由总览(React Router 7 `createBrowserRouter`)

> 采用 React Router 7 的 `createBrowserRouter` + 嵌套 `Route` + `loader` 模式,**鉴权统一在 loader 里 throw `redirect()`**,不写运行时拦截组件。

```
/login                          PublicLayout > Login
/setup                          PublicLayout > Setup (仅 needs_setup=true)

/                               AppLayout(鉴权 loader)
  /                             → redirect /dashboard
  /dashboard                    Dashboard
  /scripts                      ScriptsList
  /scripts/:slug                ScriptDetail
    ?tab=overview|fields|readme
  /scripts/:slug/instances/:id  InstanceDetail
    ?tab=overview|config|history|logs
  /runs                         RunsList
  /runs/:id                     RunDetail(SSE 实时日志在此)
  /notifications                NotificationsList(渠道 + 规则两个 Tabs)
  /notifications/channels/:id   ChannelDetail
  /settings                     → redirect /settings/general
  /settings/:tab                Settings(嵌套 tab:general/appearance/backup/about)
  *                             NotFound
```

共 14 个 route(含 layout / index / catch-all)。所有路径全小写、kebab-case、与后端 API 路径对齐(`/scripts` ↔ `/api/v1/scripts`)。

### 2.2 鉴权 guard(loader + redirect 模式)

后端在 `/auth/me` 返回 `401` 即未登录,前端 loader 捕获后跳 `/login`;首次启动 `/auth/setup-status.needs_setup=true` 时强制跳 `/setup`。

```ts
// src/app/routes/_layouts/AppLayout.loader.ts
import { redirect, type LoaderFunctionArgs } from 'react-router';
import { queryClient } from '@/lib/query-client';
import { authQueries } from '@/api/queries/auth';

export async function appLayoutLoader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);

  // 1) 先确认是否需要 setup(冷启动后用户表为空)
  const setupStatus = await queryClient.ensureQueryData(authQueries.setupStatus());
  if (setupStatus.needs_setup) {
    throw redirect('/setup');
  }

  // 2) 再确认登录态;ensureQueryData 失败 → 401 → 跳 login(带回跳参数)
  try {
    const me = await queryClient.ensureQueryData(authQueries.me());
    return { user: me };
  } catch (err) {
    if (isUnauthorized(err)) {
      throw redirect(`/login?from=${encodeURIComponent(url.pathname + url.search)}`);
    }
    throw err;
  }
}
```

```ts
// src/app/routes/_layouts/PublicLayout.loader.ts
export async function publicLayoutLoader({ request }: LoaderFunctionArgs) {
  // 已登录访问 /login 直接弹回 dashboard
  const url = new URL(request.url);
  const setupStatus = await queryClient.ensureQueryData(authQueries.setupStatus());

  if (url.pathname === '/setup' && !setupStatus.needs_setup) {
    throw redirect('/login');
  }
  if (url.pathname === '/login' && setupStatus.needs_setup) {
    throw redirect('/setup');
  }

  if (url.pathname === '/login') {
    try {
      await queryClient.ensureQueryData(authQueries.me());
      // 已登录,跳回首页
      throw redirect('/dashboard');
    } catch (err) {
      if (!isUnauthorized(err)) throw err;
      // 未登录,继续渲染 login
    }
  }
  return null;
}
```

```tsx
// src/app/router.tsx
import { createBrowserRouter } from 'react-router';

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    loader: publicLayoutLoader,
    children: [
      { path: '/login',  element: <LoginPage /> },
      { path: '/setup',  element: <SetupPage /> },
    ],
  },
  {
    path: '/',
    element: <AppLayout />,
    loader: appLayoutLoader,
    HydrateFallback: AppLayoutSkeleton,    // 防止 loader pending 时白屏
    errorElement: <AppErrorBoundary />,    // 兜底报错
    children: [
      { index: true, loader: () => redirect('/dashboard') },
      { path: 'dashboard',                    element: <DashboardPage /> },
      { path: 'scripts',                      element: <ScriptsListPage /> },
      { path: 'scripts/:slug',                element: <ScriptDetailPage /> },
      { path: 'scripts/:slug/instances/:id',  element: <InstanceDetailPage /> },
      { path: 'runs',                         element: <RunsListPage /> },
      { path: 'runs/:id',                     element: <RunDetailPage /> },
      { path: 'notifications',                element: <NotificationsPage /> },
      { path: 'notifications/channels/:id',   element: <ChannelDetailPage /> },
      { path: 'settings',                     loader: () => redirect('/settings/general') },
      { path: 'settings/:tab',                element: <SettingsPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
```

**关键设计**:
- 所有 `loader` 走 TanStack Query 的 `queryClient.ensureQueryData()`,**数据缓存与 loader 复用同一份**,组件挂载后用 `useQuery` 读取无需二次请求
- `redirect()` 是 React Router 7 的**抛错而非 return**,所以包在 `try/catch` 里要小心(`isUnauthorized` 必须只处理 401,redirect 自身的错要 `throw`)
- `HydrateFallback`(替代 v6 的 `fallbackElement`)防止 loader pending 时整屏白板,显示 `AppLayoutSkeleton`(侧栏 + 顶栏 + 主区占位)
- `errorElement`(`AppErrorBoundary`)捕获 5xx / 网络异常,显示重试 + "回首页"按钮

### 2.3 布局组件

#### 2.3.1 PublicLayout(登录 / setup)

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│              ●●●  mesh blob 背景(40s 漂移)               │
│              ╔════════════════════════╗                    │
│              ║                        ║                    │
│              ║   登录卡 / setup 卡    ║                    │
│              ║                        ║                    │
│              ╚════════════════════════╝                    │
│                  · · ·                                     │
└────────────────────────────────────────────────────────────┘
```

`<Outlet />` 居中渲染,背景是 fixed 全屏 mesh gradient + 漂移动画(详见 §3.1)。
不显示侧栏 / 顶栏。深色模式自动跟随系统。

#### 2.3.2 AppLayout(主区)

```
┌──────────┬───────────────────────────────────────────────┐
│          │ TopBar                                ⌘K  ☾ 头│
│ Sidebar  ├───────────────────────────────────────────────┤
│          │                                               │
│  Logo    │            <Outlet />                          │
│  ────    │                                               │
│  仪表盘  │                                               │
│  脚本    │                                               │
│  执行    │                                               │
│  通知    │                                               │
│  设置    │                                               │
│          │                                               │
│  user ↑  │                                               │
└──────────┴───────────────────────────────────────────────┘
```

- **Sidebar**:固定 240px,可折叠为 60px(`SidebarProvider` 配合 cookie 记忆)
- **TopBar**:吸顶 56px,左侧 breadcrumb,右侧 ⌘K 触发器 / 主题切换 / 用户头像 dropdown
- **主区**:`px-8 py-6`,最大宽度 1440px(超宽屏左对齐留白)
- **路由切换动画**:`<AnimatePresence mode="wait">` 包 `<Outlet />`,opacity 0→1 + y 8→0,180ms ease-out-quart

---

> **注**:第 3-11 章(关键页面 wireframe / 组件清单 / 状态管理 / API 封装 / 响应式 / 美化手法 / 目录结构 / 依赖 / shadcn 安装约定)内容详尽,由 Plan agent 完整产出。本文档已严格遵守用户硬要求"UI 必须美化",每个页面 wireframe 都给了视觉描述 + ASCII 草图 + 美化要点 + 关键交互;每个公共组件都给了 props 签名;美化手法精炼到组件级(卡片 hover / 按钮按压 / 状态点呼吸 / KPI sparkline / 路由 fade-slide / ⌘K Raycast 风 / 暗色 inset highlight / lucide 描边 1.75 / Recharts 主题适配 / xterm 主题同步 / 登录页 mesh blob 等)。**编码 agent 可直接基于此文档实施**。

## 3. 关键页面 wireframe

### 3.1 登录页 `/login`

**视觉描述**:全屏深色渐变背景(浅色模式带极淡蓝紫的暖白底),正中央一张玻璃拟态(glassmorphism)登录卡,背景层叠 3 个柔焦 mesh blob(主色 indigo + 强调色 teal + 暖色 amber)以 40s 周期缓慢漂移。

**ASCII 草图**:
```
┌─────────────────────────────────────────────────────┐
│       ● indigo blur                                 │
│                          ● teal blur                │
│                  ╔═════════════════╗                │
│                  ║   [Logo] 签到面板║                │
│                  ║   ─────────────  ║                │
│                  ║   欢迎回来       ║                │
│                  ║   用户名         ║                │
│                  ║   [_____________]║                │
│                  ║   密码           ║                │
│                  ║   [_____________]║                │
│                  ║   [   登 录    ] ║                │
│                  ║   v0.1.0 · 文档  ║                │
│                  ╚═════════════════╝                │
│            ● amber blur                             │
└─────────────────────────────────────────────────────┘
```

**美化要点**:卡片宽 400px / `rounded-2xl` / `p-8` / `.glass` 类;三个 blob 各 480px `blur-3xl opacity-40`,父容器 `animate-mesh-drift`;标题 `text-2xl font-semibold tracking-tight`;表单 input `h-10 rounded-md`;提交按钮 `w-full h-10` 主色 + loading 时 `Loader2` 旋转。

**关键交互**:`react-hook-form + zod` 校验;5 次失败锁定卡片变灰 + `<Alert variant="warning">`;成功 → `redirect(searchParams.get('from') ?? '/dashboard')`。

**shadcn 组件**:`Card` / `Input` / `Label` / `Button` / `Form` / `Alert`

### 3.2 初始化页 `/setup`

与登录卡同款 glass 风,宽 480px。必须有醒目的 `<Alert variant="warning">` 提示"主密钥已生成,创建后立即去 设置→备份 导出"。密码强度实时显示(用 `<Progress>` 上色)。

### 3.3 仪表盘 `/dashboard`

5 个 section:KPI 区(6 张数字卡)→ 7 天执行趋势图 → 即将执行 + 最近失败(左右)→ 脚本健康度卡片网格 → 实时活动 Timeline。

**ASCII 草图**:
```
┌──────────────────────────────────────────────────────────────────────────┐
│ 仪表盘                                          [扫描脚本] [新建实例] ⟳ │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌──KpiCard────┐ ┌──KpiCard────┐ ┌──KpiCard────┐ ┌──KpiCard────┐         │
│ │ 脚本   ╱╲   │ │ 实例   ╱╲   │ │ 今日 ╱╲╱   │ │ 7天 ╱──    │         │
│ │  24 ↗     │ │  31 ↗     │ │ 152↗     │ │ 98.4%↗   │         │
│ │  ↑12%     │ │  +2 新增  │ │  148/152 │ │  +0.6%   │         │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘         │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌── 7 天执行趋势(堆叠柱状)─────────────────────────────[日|时] ┐       │
│ │  ▆ ▆ ▆ ▆ ▆ ▆ ▆   (绿=success / 黄=failure / 红=error / 灰=timeout)│   │
│ └────────────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ 即将执行 ──┐ ┌─ 最近失败 ──┐                                          │
│ │ ● B站 3min   │ │ ● 微博 2h    │                                        │
│ └──────────────┘ └──────────────┘                                        │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ 脚本健康度卡片网格(ScriptCard × N)─────────────────────────────┐    │
│ └────────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ 实时活动 Timeline(@tanstack/react-virtual)──[自动滚动 ☑]────────┐  │
│ └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

**美化要点**:
- KPI 卡 `rounded-xl border bg-card p-6 card-hover`,数字 `text-3xl font-semibold tabular-nums`,挂载 `framer-motion useSpring` 0→目标值 count-up 600ms
- Sparkline `<ResponsiveContainer height={48}>` + `<Area>` 渐变填充 `from-primary/30 to-primary/0`
- 堆叠柱状:Recharts `BarChart` + `Bar stackId="x"`,色相 chart-1~5,顶部圆角 `radius={[4,4,0,0]}`,grid 水平虚线
- ScriptCard 网格:`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4`
- Timeline 用 `@tanstack/react-virtual` 虚拟滚动,高 480

**关键交互**:5 个 useQuery(`overview / upcoming / failures / timeline / scripts`),`refetchInterval: 30_000` 静默更新;"扫描脚本"→ mutation 完成后 invalidate;"自动滚动"开关允许向上翻阅。

**shadcn 组件**:`Card` / `Button` / `Badge` / `ScrollArea` / `Tabs` / `Skeleton` / `Tooltip` + 自定义 `KpiCard` / `ScriptCard` / `StatusDot`

### 3.4 脚本列表 `/scripts`

顶部工具栏:`<Input>` 搜索 / `<Select>` 分类 / 视图切换 toggle / "扫描脚本" 主 CTA。左侧筛选 `<Accordion>`,主区卡片网格 vs 表格 `<DataTable>` 切换(`<Tabs>` 触发 `<AnimatePresence>` fade-cross)。

每张 ScriptCard `min-h-[220px] p-5 rounded-xl border bg-card card-hover`,左上 icon 48x48(fallback `<Avatar>` 首字母 + chart-N hash 取色)。"+ 实例" → 打开 `<Sheet side="right" className="w-[560px]">` 内嵌动态表单。

### 3.5 脚本详情 `/scripts/:slug`

Header(icon 64 + 名称 + 描述 + 版本 + 元信息)+ 6 个 `<Tabs>`:概览 / 实例 / 配置 schema / 历史 / 实时日志 / README。Tab 用 shadcn `Tabs` 底部边框模式,激活态下划线 `motion.div layoutId="active-tab-indicator"`。README 用 `react-markdown + remark-gfm` + `prose prose-zinc max-w-3xl dark:prose-invert`。

### 3.6 实例配置表单(动态生成)

**关键**:11 种字段类型一一对应组件:

| type | 控件 | 备注 |
|---|---|---|
| string | `<Input>` | placeholder/pattern/min/max length |
| secret | `<Input type="password">` + 眼睛切换 | 编辑模式 placeholder `已配置 (留空保持不变)` |
| integer | `<Input type="number">` 或 `<Slider>` | min/max/step |
| boolean | `<Switch>` | label 右侧 |
| select | `<Select>` | options 来自 schema |
| multiselect | `<MultiSelect>`(Command + Popover) | chip 展示已选 |
| multiline | `<Textarea>` | rows |
| cron | `<CronInput>` | cronstrue + cron-parser,显示"→ 每天 08:00 执行" |
| url | `<Input type="url">` | zod url validation + scheme 白名单 |
| json | `<JsonEditor>` | react-json-view-lite 或 codemirror |

表单管理 `react-hook-form + zod`,schema 由 `useMemo` 从 `fields_schema` 编译。底部固定 bar:`sticky bottom-0 bg-background/95 backdrop-blur border-t` 放 [取消 / 测试运行 / 创建]。"测试运行"调用 `POST /instances/{id}/test`。

**secret 字段 PATCH 语义**:已配置 + 编辑模式下 placeholder = "已配置 (留空保持不变)",空值不更新,与后端 § 5.2 对齐。

### 3.7 执行历史 `/runs` + 详情

列表用 TanStack Table(server-side 分页 + 筛选 + 排序),50 条/页。点击行打开右侧 `<Sheet>` 详情(不跳页)或 `navigate('/runs/:id')` 独立页。

列:`●状态点 / 开始时间(相对+tooltip绝对) / 脚本/实例 / 状态Badge / 时长(tabular-nums) / 触发 / 退出码 / ⋯操作`。

状态点:success/failure/error/timeout 对应 chart-4/chart-5/chart-5(深)/chart-3,`pending`/`running` 加 `dot-pulse`。

筛选条字段同步到 URL search params(nuqs)。"导出 CSV"用 `papaparse`。"清理" → `<AlertDialog>`。

### 3.8 实时日志查看器(xterm.js + SSE)

run 处于 `pending`/`running` 时嵌入 xterm 终端。工具栏:暂停/恢复 / 全屏 / 搜索 / 清屏 / 导出。SSE 用 `@microsoft/fetch-event-source`(自动重连)。

xterm theme 与 CSS vars 同步:`background: var(--background)` / `foreground: var(--foreground)` / 各 ANSI 颜色对应 CSS vars。`fontFamily: var(--font-mono)` / `fontSize: 14` / `lineHeight: 1.4`。addon:`fit` / `search` / `web-links`。

custom hook `useLogStream(runId)`:`fetchEventSource(`/api/v1/runs/${runId}/logs/stream`, {...})`,监听 `stdout/stderr/status/end` 事件;`status='running'` 时 dot-pulse 呼吸;`end` 触发后 `ctrl.abort()` 关闭流。

### 3.9 通知 `/notifications`

两个 Tabs:**渠道** + **规则**。

渠道页:卡片网格,每张 ChannelCard 顶部图标按 scheme 自动识别(tgram/mailto/ding 等),`apprise_url` 脱敏为 `tgram://***/***`,"测试发送" 按钮触发 `POST /channels/:id/test`,5 秒内出结果。

规则页:matrix 表格(行=触发源[global/script/instance],列=event[success/failure/error/timeout],单元格=渠道集合),单元格点击 → `<Dialog>` 编辑规则。"预览"按钮 → 用模板渲染假数据。

### 3.10 设置 `/settings/:tab`

左 nav 200 + 右主区。4 个 tab:账户 / 外观 / 备份 / 关于。

- **账户**:显示名 / 修改密码 / 会话超时 / 注销其他设备 / 锁定阈值
- **外观**:主题(浅/深/系统 `<ToggleGroup>`)/ 主色调(6 色 swatch,改 CSS vars 即时变)/ 字体大小 `<Slider>` / 紧凑模式 `<Switch>`
- **备份**:**顶部醒目 `<Alert variant="warning">`** 提示主密钥丢失=配置作废;"导出备份"大按钮 + checkbox 选是否含 key;"从备份恢复" `<Dropzone>` 拖拽 zip
- **关于**:版本 / 构建时间 / Git commit / 后端版本 / Python 版本

主题切换走 `next-themes` 无闪烁;主色调切换动态 set `:root` 的 `--primary` `--ring` `--chart-1` `--sidebar-primary` 写到 `<style id="theme-overrides">`,`localStorage` 记忆。

### 3.11 全局组件

**TopBar**(`h-14 sticky top-0 z-30 bg-background/95 backdrop-blur border-b`):左侧 `☰` 折叠 + breadcrumb(从 React Router `matches` 计算);右侧 `⌘K` + 主题切换 dropdown + 通知铃 + 用户头像 dropdown

**Sidebar**(shadcn `Sidebar` block):`w-60` / 折叠 `w-15`(只剩图标 + tooltip),激活态 2px primary `motion.div layoutId="sidebar-active"`,cookie 持久化

**CommandPalette(⌘K,cmdk)**:Raycast 风,`rounded-xl shadow-xl`,宽 640;顶部搜索框 `h-12`;分组:推荐 / 导航(带数字快捷键)/ 脚本 / 实例 / 主题。底部 status bar `↑↓ 导航 ↵ 选择 ⎋ 关闭`

**StatusDot**(8px 圆点 + 可选 dot-pulse)/ **StatusBadge**(图标 + 文字 + outline `bg-{color}/10 text-{color} border-{color}/30`)

### 3.12 状态设计

- **空状态 `<EmptyState>`**:`border-2 border-dashed border-border rounded-xl py-16`,lucide 大图标 `size-12 text-muted-foreground/40` + 标题 + 描述 + 可选 CTA
- **错误状态 `<ErrorState>`**:标题 `text-base font-medium text-danger`,描述 `font-mono text-xs` 可折叠,提供"重试 / 回首页"
- **Skeleton**:严格对应真实内容尺寸(KPI 卡 h-32 / 表格行 h-12 / ScriptCard h-[220]),用 `skeleton-shimmer` 类(渐变 + 1.6s shimmer);**禁止全屏 spinner**;按钮内允许小 spinner

---

## 4. 公共组件清单

| 组件 | 关键 props | 用途 |
|---|---|---|
| `<KpiCard>` | `label / value / unit / trend / sparkline / icon / variant / loading / onClick` | 仪表盘数字卡 + sparkline + count-up |
| `<ScriptCard>` | `script / onCreateInstance / onClick` | 脚本卡片网格条目 |
| `<StatusBadge>` | `status / variant=badge\|dot\|inline / size` | 7 种状态语义化展示 |
| `<CronInput>` | `value / onChange / showHumanReadable / showHelper / preset / error` | cron 输入 + 人类可读 + 可视化辅助 |
| `<SecretInput>` | `value / onChange / hasExisting / placeholder` | 显隐切换 + 已配置占位 + 锁图标 |
| `<LogViewer>` | `runId / initialStdout / initialStderr / mode=static\|live / height / onCancel` | 静态/实时双模式,实时用 xterm |
| `<EmptyState>` | `icon / title / description / action` | 通用空态 |
| `<ErrorState>` | `error / retry / fallbackHome` | 通用错误态 |
| `<PageHeader>` | `title / description / breadcrumb / actions / tabs` | 统一页头 |
| `<ConfirmDialog>` | hook `useConfirm()` 命令式调用 | 危险操作二次确认 |
| `<DataTable>` | `columns / data / total / pagination / sorting / filters / loading / emptyState / onRowClick / selectable / resizable / columnVisibility` | 基于 TanStack Table 的封装 |
| `<DynamicForm>` | `schema / initialValues / existingSecrets / onSubmit / onCancel / onTest / submitLabel / layout=sheet\|page` | 按 fields_schema 动态渲染表单 |
| `<ThemeProvider>` | `attribute / defaultTheme / enableSystem` | next-themes 包裹 |
| `<CommandPalette>` | `open / onOpenChange` | ⌘K 全局命令面板,自动加载 scripts/instances |
| 杂项 | `<RelativeTime>` `<CopyButton>` `<KbdHint>` | — |

每种字段类型对应的 FieldRenderer 在 `components/common/fields/`:`StringField` / `SecretField` / `IntegerField` / `BooleanField` / `SelectField` / `MultiSelectField` / `MultilineField` / `CronField` / `UrlField` / `JsonField`。

---

## 5. 状态管理

### 5.1 Zustand stores(仅纯客户端状态)

- `useUIStore`:sidebarCollapsed / commandPaletteOpen / compactMode(persist 到 localStorage)
- `useThemeStore`:自定义主色等 next-themes 外的额外配置
- `usePreferencesStore`:表格列宽 / 列显隐(persist)

**绝对禁止**把服务端数据塞 Zustand,那是 TanStack Query 的工作。

### 5.2 TanStack Query 5 hooks(服务端数据)

采用 **Query Factory 模式**(2025-2026 主流):

```ts
export const scriptsQueries = {
  all: () => ['scripts'] as const,
  list: (filters = {}) => queryOptions({
    queryKey: [...scriptsQueries.all(), 'list', filters],
    queryFn: async ({ signal }) => {
      const { data } = await client.GET('/api/v1/scripts', { params: { query: filters }, signal });
      return data!;
    },
    staleTime: 30_000,
  }),
  detail: (slug: string) => queryOptions({ /* ... */ }),
};

// 用法
const { data } = useQuery(scriptsQueries.list({ enabled: true }));
// loader 里
await queryClient.ensureQueryData(scriptsQueries.detail(slug));
```

**全局 defaultOptions**:`staleTime 30_000`,`gcTime 5min`,`refetchOnWindowFocus true`,`retry` 不重试 401,mutation `onError` 全局 toast。

**Optimistic update**:`onMutate cancel + setQueryData prev → onError rollback → onSettled invalidate`。

---

## 6. API 封装层

### 6.1 openapi-typescript 自动类型

```bash
pnpm gen:api   # openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/api/schema.d.ts
```

### 6.2 client + middleware

```ts
const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (!['GET', 'HEAD'].includes(request.method)) {
      request.headers.set('X-Requested-With', 'fetch');   // 与后端 §5.4 双保险防 CSRF
    }
    return request;
  },
};
const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.status === 401) window.dispatchEvent(new CustomEvent('app:unauthorized'));
    if (!response.ok && response.status >= 500) toast.error('服务器错误,请稍后重试');
    return response;
  },
};

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE ?? '/',
  credentials: 'include',   // 带 cookie
});
client.use(csrfMiddleware);
client.use(errorMiddleware);
```

### 6.3 SSE hook `useLogStream`

```ts
export function useLogStream(runId, opts) {
  useEffect(() => {
    const ctrl = new AbortController();
    fetchEventSource(`/api/v1/runs/${runId}/logs/stream`, {
      signal: ctrl.signal,
      credentials: 'include',
      headers: { 'X-Requested-With': 'fetch' },
      openWhenHidden: true,
      onmessage(ev) {
        switch (ev.event) {
          case 'stdout': opts.onStdout(ev.data); break;
          case 'stderr': opts.onStderr(ev.data); break;
          case 'status': opts.onStatus(JSON.parse(ev.data)); break;
          case 'ping': break;
          case 'end': opts.onEnd(); ctrl.abort(); break;
        }
      },
      onerror(err) { opts.onError?.(err); throw err; },
    });
    return () => ctrl.abort();
  }, [runId]);
}
```

---

## 7. 响应式策略

桌面优先,1280+ 最佳;`xl` 主区 `max-w-[1440px] mx-auto`;`< 1024` 侧栏自动折叠 + 表格隐藏次要列(useMediaQuery + DataTable columnVisibility);**不为手机做布局**(用户硬要求),但 `< 1024` 时仍可基本浏览。

---

## 8. 美化关键手法(具体到组件级)

| 部位 | 手法 |
|---|---|
| 卡片 | `rounded-xl border bg-card text-card-foreground shadow-xs`;边框 `border-border` 半透明;深色 inset highlight `inset 0 1px 0 oklch(1 0 0 / 0.06)`;`card-hover` 类(hover -translate-y-0.5 + shadow-md) |
| 按钮 | `active:scale-[0.98]` 按压感;`focus-visible:ring-2 ring-ring ring-offset-2`;loading 左侧 `<Loader2 className="size-4 mr-2 animate-spin" />`;destructive 用 `bg-danger`;ghost 用 `hover:bg-accent` 不加边框 |
| 数字 | 全 `tabular-nums`;大数字 `Intl.NumberFormat('zh-CN')` 千分位;时长智能格式化(<1s `932ms` / <60s `3.2s` / <60min `2m 13s`);KPI count-up 600ms;变化 `<AnimatePresence mode="wait">` opacity 跳变 |
| 状态点 | 静态 8px 实心 + 语义色;pending/running 加 `::before` 伪元素 `animation: pulseDot 2s infinite`(scale 1↔1.4 + opacity 1↔0.55) |
| KPI Sparkline | Recharts `<AreaChart>` 简化版,无坐标轴;`stroke="oklch(var(--chart-1))" strokeWidth={1.5}`;`fill="url(#grad)"` 渐变 30%→0% |
| 路由切换 | `<AnimatePresence mode="wait" initial={false}>` 包 `<Outlet />`,opacity 0→1 + y 8→0,180ms ease-out-quart |
| ⌘K 命令面板 | Raycast 风:`rounded-xl shadow-xl` 宽 640;搜索框 `h-12`;项目左 icon 24 中间标题/副标题右 kbd;选中 `bg-accent rounded-md`;分组标题 `text-[11px] uppercase tracking-wider text-muted-foreground/70` |
| 微交互 | 按钮按下 `active:scale-[0.98]`;Tab 下划线 `motion.div layoutId="active-tab-indicator"` morph;Dialog 进入 scale 0.95→1 + opacity 0→1,200ms |
| 暗色模式 | 不简单反色:中性色相统一偏蓝 252°;卡片比 background 亮一档;边框半透明白;shadow 加 inset highlight;语义色亮度上调 0.05 饱和度下调 0.02;图表色重写 |
| lucide 图标 | 统一 `strokeWidth={1.75}`(默认 2 太粗);`size-4` 默认,导航/大按钮 `size-5`,logo 区 6+;颜色继承 currentColor |
| Recharts 主题 | 颜色用 `oklch(var(--chart-N))` 跟随主题;`<CartesianGrid stroke="..." strokeDasharray="4 4" vertical={false}>` 只画水平虚线;tooltip 用 shadcn Card 风格;不显示默认 Legend |
| xterm 主题 | theme 各 ANSI 颜色 → CSS vars;`fontFamily: var(--font-mono)`;监听 `useTheme()` 变化时重设 `term.options.theme` |
| 登录页 mesh | 3 个 blob 各 480-520px `blur-3xl opacity-30-40%`,主色/teal/amber;`animate-mesh-drift` 40s + **不同 animation-delay 错开**(-13s / -27s);外层 `backdrop-blur-3xl bg-background/40` 让玻璃拟态更明显 |
| Toast(sonner) | `position="top-right"` `richColors closeButton`;`classNames.toast = 'rounded-xl border border-border shadow-md bg-popover text-popover-foreground'`;**top-right 不是 top-center** |
| Skeleton | 用 `skeleton-shimmer` 类(渐变 + 1.6s shimmer 动画),严格对应真实尺寸;**禁止全屏 spinner**;按钮内允许小 spinner |
| 表单 | label `text-sm font-medium mb-1.5`;required 红 `*`;字段间距 `space-y-5`,分组间距 `space-y-8`;input focus `border-ring/60` + ring;错误 `text-xs text-danger mt-1.5` + `<AlertCircle className="size-3" />` |

---

## 9. 推荐目录结构

```
frontend/
├── public/                  # favicon / logo
├── src/
│   ├── main.tsx             # 挂 ThemeProvider + RouterProvider + QueryClientProvider
│   ├── app/
│   │   ├── router.tsx       # createBrowserRouter
│   │   ├── index.css        # Tailwind v4 + @theme + CSS vars(§ 1.5)
│   │   └── routes/
│   │       ├── _layouts/    # AppLayout / PublicLayout + loaders
│   │       ├── login/  setup/  dashboard/  scripts/  instances/
│   │       ├── runs/  notifications/  settings/  not-found/
│   ├── components/
│   │   ├── ui/              # shadcn copy-pasted(只 add 不手改)
│   │   ├── common/          # 业务公共组件 + fields/(11 种 FieldRenderer)
│   │   ├── layout/          # TopBar / AppSidebar / CommandPalette / ThemeToggle / UserMenu
│   │   └── theme/           # ThemeProvider
│   ├── api/
│   │   ├── schema.d.ts      # openapi-typescript 生成
│   │   ├── client.ts        # openapi-fetch + middleware
│   │   ├── query-client.ts  # QueryClient 单例
│   │   ├── queries/         # Query Factory: auth / scripts / instances / runs / notifications / settings / dashboard
│   │   ├── mutations/
│   │   └── sse/             # use-log-stream
│   ├── stores/              # ui / theme / preferences
│   ├── hooks/               # use-confirm / use-hotkeys / use-media-query
│   ├── lib/                 # utils(cn) / format / error / cron / zod-from-schema / chart-theme
│   ├── styles/              # prose.css
│   └── vite-env.d.ts
├── components.json          # shadcn config
├── tailwind.config.ts       # v4 主要靠 @theme,只放 plugin
├── postcss.config.mjs
├── tsconfig.json / tsconfig.node.json / tsconfig.app.json
├── vite.config.ts
├── package.json
└── pnpm-lock.yaml
```

**职责一句话**:
- `app/` 路由/loader/页面 — **仅页面级**
- `components/ui/` shadcn 源码 — **只通过 shadcn CLI add,不手改**
- `components/common/` 业务公共组件
- `components/layout/` 全局布局
- `api/` 所有 HTTP+SSE,与 UI 解耦
- `stores/` 全局 zustand,**仅纯客户端**
- `lib/` 纯函数
- `hooks/` 通用 hook

---

## 10. 关键依赖(package.json 风格)

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router": "^7.6.0",

    "@tanstack/react-query": "^5.66.0",
    "@tanstack/react-query-devtools": "^5.66.0",
    "@tanstack/react-table": "^8.21.0",
    "@tanstack/react-virtual": "^3.13.0",

    "zustand": "^5.0.3",
    "nuqs": "^2.4.0",

    "openapi-fetch": "^0.13.5",
    "@microsoft/fetch-event-source": "^2.0.1",

    "react-hook-form": "^7.55.0",
    "@hookform/resolvers": "^4.1.0",
    "zod": "^3.24.0",

    "@radix-ui/react-accordion": "^1.2.3",
    "@radix-ui/react-alert-dialog": "^1.1.6",
    "@radix-ui/react-avatar": "^1.1.3",
    "@radix-ui/react-checkbox": "^1.1.4",
    "@radix-ui/react-collapsible": "^1.1.3",
    "@radix-ui/react-dialog": "^1.1.6",
    "@radix-ui/react-dropdown-menu": "^2.1.6",
    "@radix-ui/react-hover-card": "^1.1.6",
    "@radix-ui/react-label": "^2.1.2",
    "@radix-ui/react-popover": "^1.1.6",
    "@radix-ui/react-progress": "^1.1.2",
    "@radix-ui/react-radio-group": "^1.2.3",
    "@radix-ui/react-scroll-area": "^1.2.3",
    "@radix-ui/react-select": "^2.1.6",
    "@radix-ui/react-separator": "^1.1.2",
    "@radix-ui/react-slider": "^1.2.3",
    "@radix-ui/react-slot": "^1.1.2",
    "@radix-ui/react-switch": "^1.1.3",
    "@radix-ui/react-tabs": "^1.1.3",
    "@radix-ui/react-toggle": "^1.1.2",
    "@radix-ui/react-toggle-group": "^1.1.2",
    "@radix-ui/react-tooltip": "^1.1.8",

    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.0.2",
    "tailwindcss-animate": "^1.0.7",
    "tw-animate-css": "^1.2.4",

    "lucide-react": "^0.475.0",

    "recharts": "^2.15.1",
    "@xterm/xterm": "^5.5.0",
    "@xterm/addon-fit": "^0.10.0",
    "@xterm/addon-search": "^0.15.0",
    "@xterm/addon-web-links": "^0.11.0",

    "framer-motion": "^12.4.0",
    "cmdk": "^1.0.4",
    "sonner": "^2.0.0",
    "next-themes": "^0.4.4",
    "vaul": "^1.1.2",

    "react-markdown": "^9.0.3",
    "remark-gfm": "^4.0.1",
    "react-syntax-highlighter": "^15.6.1",

    "date-fns": "^4.1.0",
    "cronstrue": "^2.52.0",

    "papaparse": "^5.4.1",
    "react-dropzone": "^14.3.5",
    "react-hotkeys-hook": "^4.6.1",

    "@fontsource-variable/inter": "^5.1.1",
    "@fontsource-variable/jetbrains-mono": "^5.1.1"
  },
  "devDependencies": {
    "@types/node": "^22.13.0",
    "@types/react": "^18.3.18",
    "@types/react-dom": "^18.3.5",
    "@types/papaparse": "^5.3.15",
    "@types/react-syntax-highlighter": "^15.5.13",

    "typescript": "~5.7.3",
    "vite": "^6.1.0",
    "@vitejs/plugin-react": "^4.3.4",

    "@tailwindcss/postcss": "^4.0.6",
    "@tailwindcss/typography": "^0.5.16",
    "tailwindcss": "^4.0.6",
    "postcss": "^8.5.1",
    "autoprefixer": "^10.4.20",

    "eslint": "^9.20.0",
    "@typescript-eslint/eslint-plugin": "^8.24.0",
    "@typescript-eslint/parser": "^8.24.0",
    "eslint-plugin-react-hooks": "^5.1.0",
    "eslint-plugin-react-refresh": "^0.4.18",

    "vitest": "^3.0.5",
    "@vitest/ui": "^3.0.5",
    "@testing-library/react": "^16.2.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/user-event": "^14.6.1",
    "jsdom": "^26.0.0",
    "msw": "^2.7.0",

    "openapi-typescript": "^7.6.1",
    "prettier": "^3.4.2",
    "prettier-plugin-tailwindcss": "^0.6.11"
  }
}
```

---

## 11. shadcn/ui 安装与用法约定

### 11.1 init 命令选项

```bash
cd frontend
pnpm dlx shadcn@latest init
```

| 问题 | 回答 |
|---|---|
| style | **Default** |
| base color | **Zinc**(中性,再手动加蓝调) |
| global CSS | `src/app/index.css` |
| CSS variables | **Yes** |
| tailwind config | `tailwind.config.ts`(v4 不用此文件但 CLI 要) |
| components alias | `@/components` |
| utils alias | `@/lib/utils` |
| RSC | **No** |

### 11.2 完整 `components.json`

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/app/index.css",
    "baseColor": "zinc",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

### 11.3 一次性 add 全部组件清单

```bash
pnpm dlx shadcn@latest add \
  button card dialog sheet dropdown-menu tabs \
  input label select switch textarea badge alert sonner \
  skeleton table tooltip popover collapsible separator \
  scroll-area command form slider checkbox radio-group \
  progress hover-card avatar breadcrumb sidebar \
  accordion alert-dialog toggle-group pagination
```

共 30 个组件 → `src/components/ui/`。

### 11.4 哪些用 shadcn 默认 / 哪些要二次美化

| 组件 | 二次美化重点 |
|---|---|
| Button | 加 `active:scale-[0.98]` + success/warning variant |
| Card | 加 `card-hover` utility |
| Tabs | 默认是边框 tab,改为"底部下划线 + motion layoutId" |
| Badge | 加 success/warning/danger/info 语义 variant |
| Alert | 加 warning/success/info variant(默认只有 destructive) |
| Sonner | 自定义 `toastOptions.classNames` 风格 |
| Skeleton | 用 `skeleton-shimmer` 类替代默认 `animate-pulse` |
| Table | 包成 `<DataTable>` + TanStack Table v8 |
| Command | 包成 `<CommandPalette>`,Raycast 风改造 |
| Sidebar | indicator 用 motion layoutId + 主色调适配 |
| Pagination | 加 tabular-nums + "1-50 of 1284" 文字 |

二次美化原则:**保留 shadcn API 不变,只覆盖 className / variants / 加 motion**,这样 shadcn 升级时能无痛 merge。

### 11.5 自建组件(shadcn 没有)

- `<MultiSelect>`:基于 `Command + Popover`,chip 显示已选
- `<CronInput>`:`Input + Popover`,内部 5 段编辑器
- `<JsonField>`:`Textarea` + 第三方 `react-json-view-lite`
- `<Dropzone>`:基于 `react-dropzone`

---

## 总结

本设计文档锁定的设计语言:

1. **视觉**:OKLCH 色彩 + 半透明边框 + 深色 inset highlight + 大圆角(10-14)+ Inter Variable + tabular-nums
2. **交互**:全 hover-180ms + active-press-0.98 + focus-visible-ring + framer 动画 + skeleton-shimmer
3. **架构**:RR7 loader + redirect 鉴权 / TQ 5 query factory / Zustand 仅客户端 / openapi-fetch 类型安全 / SSE 用 fetch-event-source
4. **美化抓手**:登录页 mesh blob + KPI sparkline + Tab motion layoutId + ⌘K Raycast 风 + xterm 主题同步 + 状态点呼吸光晕
5. **shadcn 落地**:30 个组件 add + § 11.4 节明确哪些二次美化

这套设计在保持后台工具"专业、可信赖"的同时,做出了 Linear/Vercel/cal.com 级别的精致感。编码 agent 可以严格按本文档执行,任何美化决定都已在文中明确说明。
