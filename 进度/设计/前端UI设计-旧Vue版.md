# 签到脚本聚合管理面板 — 前端 UI/UX 设计文档 v1.0

> 本文档为编码 Agent 的设计契约。技术栈已锁定:Vue 3 + Vite + TS + Pinia + Vue Router 4 + Element Plus(重度美化)。后端 FastAPI + REST + SSE。
>
> 设计目标:做一个克制、现代、有温度的后台工具,拒绝"默认 Element Plus 灰扁平外观"。参考调性 Linear / Vercel / Raycast / shadcn/ui。

---

## 1. 视觉风格指南

### 1.1 设计调性

定调五个形容词:**克制、现代、精致、安静、可信赖**。

**克制(Restrained)**:这是给个人/小团队 7×24 长期挂着看的工具,不能花哨。所有装饰都必须服务于信息层级——禁止纯装饰渐变、禁止无意义图形、禁止过度动画。颜色只在"需要被注意"的位置出现:状态徽标、CTA 按钮、当前选中项。其余地方用大量中性灰阶和留白。

**现代(Modern)**:抛弃 2010 年代企业后台那种"白底+灰线+彩色填充按钮+灰扁平表格"的糟糕组合。我们走 2024-2025 的当代审美:大圆角(8-12px 起)、半透明分层(border 用 rgba 白/黑)、柔和阴影、精致字体(Inter)、Tabular Numbers、深色模式作为一等公民而非附属。

**精致(Refined)**:一切细节都需要打磨。按钮 hover 要有 200ms 的颜色与轻微抬升;开关切换要有 spring easing;数字变化要有 count-up 动效;状态点要有"呼吸"光晕;切换 tab 要有 fade-slide。每个微交互单独看微不足道,叠在一起就是"高级感"的来源。

**安静(Quiet)**:这个工具会被长时间盯着看。配色饱和度普遍较低,文字与背景对比度精确控制(WCAG AA 但不要过头到刺眼);loading 用 skeleton 而非 spinner;通知 toast 默认安静地从右上角滑入而非闪烁;深色模式不使用纯黑 #000,而是 #0B0D10 这种偏蓝的 near-black,搭配 #E6E8EB 的 near-white 文字,长时间观看不疲劳。

**可信赖(Trustworthy)**:这是个会自动跑脚本、发通知、管密钥的工具。视觉必须传达"它不会坏、不会乱来"的稳重感。具体手段:统一的间距栅格(4px base),严格的字号体系(只有 8 档,不许临时新增),明确的状态语义色(success/warning/danger/info 四色固定),禁止滥用动画(只在交互反馈和数据变化时使用)。

### 1.2 配色方案

色阶按 50-900 命名,数值越大颜色越深(浅色模式下);深色模式下色阶语义反转使用。

#### 主色 Brand(Indigo 系)

选 indigo 作主色,理由:不像纯蓝那么 corporate,带一点紫的温度,在浅色与深色模式下都不刺眼,且与中文字体的笔画粗细搭配自然。

| Token | Hex | 用途 |
|---|---|---|
| brand-50 | `#EEF0FF` | 浅色 hover 底 / 深色高对比文字背景 |
| brand-100 | `#DCE0FE` | 浅色选中项底 |
| brand-200 | `#BCC4FD` | 边框高亮 |
| brand-300 | `#95A2FB` | disabled 主按钮 |
| brand-400 | `#7281F7` | hover 状态 |
| brand-500 | `#5865F2` | **主色基准**(主按钮、链接、focus ring) |
| brand-600 | `#4751D8` | 主按钮按下 |
| brand-700 | `#3A41B0` | |
| brand-800 | `#2E338A` | |
| brand-900 | `#22265F` | 深色模式主按钮底 |

#### 强调色 Accent(Teal 系,用于次要 CTA、统计图配色)

| Token | Hex |
|---|---|
| accent-50 | `#E6FBF7` |
| accent-100 | `#C2F4EA` |
| accent-300 | `#5DDDC0` |
| accent-500 | `#14B8A6` |
| accent-700 | `#0E8A7C` |
| accent-900 | `#0A4A43` |

#### 语义色

均给出 50/500/700 三档,500 是基准。

**Success(Emerald)**

| Token | Hex |
|---|---|
| success-50 | `#ECFDF5` |
| success-500 | `#10B981` |
| success-700 | `#047857` |

**Warning(Amber)**

| Token | Hex |
|---|---|
| warning-50 | `#FFFBEB` |
| warning-500 | `#F59E0B` |
| warning-700 | `#B45309` |

**Danger(Rose)** — 选 rose 而非 red,因为 rose 在深色模式更柔和

| Token | Hex |
|---|---|
| danger-50 | `#FFF1F2` |
| danger-500 | `#F43F5E` |
| danger-700 | `#BE123C` |

**Info(Sky)**

| Token | Hex |
|---|---|
| info-50 | `#F0F9FF` |
| info-500 | `#0EA5E9` |
| info-700 | `#0369A1` |

#### 中性色阶 Neutral

浅色模式以暖灰(zinc 偏 stone),深色模式以冷灰(zinc 偏 slate)。这是高级感的关键:不要用纯灰 `#808080`,纯灰看起来很塑料。

**浅色模式中性色(背景到文字)**

| Token | Hex | 典型用法 |
|---|---|---|
| neutral-0 | `#FFFFFF` | 卡片底色、Modal 底色 |
| neutral-50 | `#FAFAF9` | 页面底色 |
| neutral-100 | `#F4F4F2` | 输入框底、侧栏底 |
| neutral-200 | `#E7E7E4` | 分割线、边框 |
| neutral-300 | `#D4D4D1` | 禁用边框 |
| neutral-400 | `#A8A8A4` | 占位符文字、icon 弱 |
| neutral-500 | `#737370` | 次要文字 |
| neutral-600 | `#52524F` | |
| neutral-700 | `#3F3F3D` | 正文文字 |
| neutral-800 | `#27272A` | 标题文字 |
| neutral-900 | `#18181B` | 强调文字、品牌 logo |

**深色模式中性色(背景到文字)**

| Token | Hex | 典型用法 |
|---|---|---|
| neutral-0 | `#0B0D10` | 页面底色(near-black,不用纯黑) |
| neutral-50 | `#111418` | 卡片底色 |
| neutral-100 | `#171A1F` | 输入框底、侧栏底 |
| neutral-200 | `#1F232A` | 卡片 hover 底 |
| neutral-300 | `#2A2F38` | 边框、分割线 |
| neutral-400 | `#3D434E` | 禁用边框 |
| neutral-500 | `#6B7280` | 占位符 |
| neutral-600 | `#9CA3AF` | 次要文字 |
| neutral-700 | `#D1D5DB` | 正文 |
| neutral-800 | `#E6E8EB` | 标题 |
| neutral-900 | `#F4F5F7` | 强调文字 |

**深色模式细节注意**:边框统一改用 `rgba(255,255,255,0.06)` 这类半透明白,而不是固定灰色——这样在不同灰度的卡片上自然融入。阴影改用 `rgba(0,0,0,0.4)+`,且额外加一层 inner highlight `inset 0 1px 0 rgba(255,255,255,0.04)` 让卡片边缘有"被打亮"的精致感。

### 1.3 字体

```
font-family-sans: 'Inter', 'HarmonyOS Sans SC', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
font-family-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace
font-family-numeric: 'Inter', system-ui, sans-serif  // 配合 font-feature-settings: 'tnum' 1, 'cv11' 1
```

Inter 必须本地化(self-hosted)而非 Google Fonts CDN,因为部署在自己的服务器上;并使用 `Inter Variable` 单文件。中文 fallback 优先 HarmonyOS Sans SC(开源、免商用、笔形清晰),退化到系统的 PingFang SC(macOS)和 Microsoft YaHei(Windows)。

代码字体用 JetBrains Mono(连字开启 `'liga' 1`),日志查看器和 cron 输入框使用。

数字一律开启 `font-feature-settings: 'tnum' 1`(等宽数字),否则统计区跳数会左右位移,非常不专业。

### 1.4 字号体系

8 档,line-height 与字重也固定。**禁止在组件里临时使用其他字号**。

| Token | font-size | line-height | font-weight | 用途 |
|---|---|---|---|---|
| text-xs | 12px | 16px | 500 | 徽标、tag、辅助元信息 |
| text-sm | 13px | 20px | 400 | 表单 label、次要文字、按钮文字 |
| text-base | 14px | 22px | 400 | 正文默认 |
| text-lg | 16px | 24px | 400 | 卡片标题、表单大输入 |
| text-xl | 18px | 28px | 600 | section 标题 |
| text-2xl | 22px | 32px | 600 | 页面副标题 |
| text-3xl | 28px | 36px | 700 | 页面主标题、KPI 数字 |
| text-4xl | 36px | 44px | 700 | 登录页大标题、大型 KPI |

**关键**:正文用 14px 而不是 16px,因为后台密度需求高,但 line-height 给到 22px(1.57)留出呼吸感。所有标题(xl 以上)字间距收紧 `letter-spacing: -0.01em`,让标题更紧致现代。

### 1.5 间距 Token

4px 为基础单位,严格执行。

```
space-0:   0
space-1:   4px
space-2:   8px
space-3:   12px
space-4:   16px
space-6:   24px
space-8:   32px
space-12:  48px
space-16:  64px
space-24:  96px
```

常用组合:卡片内边距 `space-6`(24px),卡片之间间距 `space-4`(16px),页面级容器内边距 `space-8`(32px),section 之间垂直间距 `space-12`(48px)。

### 1.6 圆角

偏圆,显年轻和现代。

```
radius-sm:   6px    // tag、徽标、小按钮
radius-md:   8px    // 输入框、按钮
radius-lg:   12px   // 卡片、Modal、抽屉
radius-xl:   16px   // 大型容器、空状态卡
radius-2xl:  24px   // 登录卡片
radius-full: 9999px // pill、头像、状态点
```

**绝对禁止**:0px 直角(过时)、4px(太小看起来像 Bootstrap)。

### 1.7 阴影体系

每档有浅色和深色两套数值。深色模式不能简单加深,否则会"糊一片",要降低不透明度并添加 inset highlight。

**浅色模式**

```
shadow-sm:  0 1px 2px 0 rgba(16, 24, 40, 0.05)
shadow-md:  0 4px 8px -2px rgba(16, 24, 40, 0.08), 0 2px 4px -2px rgba(16, 24, 40, 0.04)
shadow-lg:  0 12px 24px -8px rgba(16, 24, 40, 0.12), 0 4px 8px -4px rgba(16, 24, 40, 0.06)
shadow-xl:  0 24px 48px -12px rgba(16, 24, 40, 0.18)
```

**深色模式**

```
shadow-sm:  0 1px 2px 0 rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.03)
shadow-md:  0 4px 8px -2px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.04)
shadow-lg:  0 12px 24px -8px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.05)
shadow-xl:  0 24px 48px -12px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.06)
```

`shadow-sm` 用于平静卡片,`shadow-md` 用于 hover 抬升,`shadow-lg` 用于 popover/dropdown,`shadow-xl` 用于 Modal。

额外定义 `shadow-glow-brand`(focus ring 的发光):
- 浅色:`0 0 0 3px rgba(88, 101, 242, 0.16)`
- 深色:`0 0 0 3px rgba(88, 101, 242, 0.32)`

### 1.8 过渡动画

```
duration-fast:    120ms   // 微反馈(按钮 hover 颜色)
duration-base:    200ms   // 默认(transform、阴影、透明度)
duration-slow:    320ms   // 抽屉、Modal 进入
duration-slowest: 480ms   // 路由切换、骨架收起

easing-standard:  cubic-bezier(0.4, 0, 0.2, 1)    // 默认
easing-decelerate:cubic-bezier(0, 0, 0.2, 1)      // 进入
easing-accelerate:cubic-bezier(0.4, 0, 1, 1)      // 离开
easing-spring:    cubic-bezier(0.34, 1.56, 0.64, 1) // 开关、弹性反馈
```

**统一规则**:任何元素的 hover/focus/active 状态变化 ≤ 200ms;Modal/抽屉/路由切换在 320ms 左右;不超过 480ms 的动画可以接受;>500ms 几乎一律拒绝(除非是数据加载占位)。

---

## 2. 页面清单与路由表

### 2.1 路由表

| path | name | component(异步加载) | meta.requiresAuth | meta.layout | meta.title |
|---|---|---|---|---|---|
| `/login` | `login` | `pages/auth/Login.vue` | false | PublicLayout | 登录 |
| `/setup` | `setup` | `pages/auth/Setup.vue` | false | PublicLayout | 初始化 |
| `/` | `root` | redirect → `/dashboard` | — | — | — |
| `/dashboard` | `dashboard` | `pages/dashboard/Dashboard.vue` | true | AppLayout | 仪表盘 |
| `/scripts` | `scripts` | `pages/scripts/ScriptList.vue` | true | AppLayout | 脚本 |
| `/scripts/:slug` | `script-detail` | `pages/scripts/ScriptDetail.vue` | true | AppLayout | 脚本详情 |
| `/scripts/:slug/instances/:id` | `instance-detail` | `pages/scripts/InstanceDetail.vue` | true | AppLayout | 实例详情 |
| `/runs` | `runs` | `pages/runs/RunList.vue` | true | AppLayout | 执行历史 |
| `/runs/:id` | `run-detail` | `pages/runs/RunDetail.vue` | true | AppLayout | 执行详情 |
| `/notifications` | `notifications` | `pages/notifications/NotificationHub.vue` | true | AppLayout | 通知 |
| `/notifications/channels/:id` | `channel-detail` | `pages/notifications/ChannelDetail.vue` | true | AppLayout | 通知渠道详情 |
| `/settings` | `settings` | `pages/settings/Settings.vue` | true | AppLayout | 设置 |
| `/settings/:tab` | `settings-tab` | `pages/settings/Settings.vue` | true | AppLayout | 设置 |
| `/:catchAll(.*)` | `not-found` | `pages/error/NotFound.vue` | false | AppLayout(若已登录)/PublicLayout | 404 |

### 2.2 鉴权 Guard 流程

`router.beforeEach` 内部执行流程:

1. 读取 Pinia `useAuthStore()`
2. 若访问的是 `requiresAuth: true` 的路由:
   - `auth.token` 不存在 → 跳 `/login?redirect={fullPath}`
   - `auth.token` 存在但 `auth.user` 为空 → 调用 `auth.fetchMe()`,失败(401)则清 token 跳登录
3. 若访问 `/login` 或 `/setup` 但已登录 → 跳 `/dashboard`
4. 若 `/setup` 路由:先调用 `GET /api/setup-status`,若已完成初始化则跳 `/login`,否则放行
5. 设置 `document.title = ${meta.title} · 签到管家`

### 2.3 布局类型

- **PublicLayout**:全屏背景(浅色用淡渐变,深色用近黑+微噪点),内容垂直水平居中。无侧栏、无顶栏。右上角只放主题切换按钮。用于 `/login`、`/setup` 和未登录态的 404。
- **AppLayout**:经典 sidebar + topbar + main content 三段式。
  - 左侧 sidebar(默认展开 240px,折叠 64px,可记忆)
  - 顶部 topbar(56px 高,固定)
  - 主内容区(min-width 1024px,max-width 1440px 居中,padding 32px)
  - 右下角 toast 容器
  - 全局 ⌘K 命令面板挂载点

---

## 3. 关键页面 wireframe

### 3.1 登录页 `/login`

#### 视觉描述

整页采用 PublicLayout。背景做两层:

- 底层:浅色模式 `linear-gradient(135deg, #FAFAF9 0%, #F4F4F2 100%)`,深色模式 `radial-gradient(ellipse at top, #171A1F 0%, #0B0D10 70%)`
- 上层:一个柔和的 mesh blob——浅色模式两个朦胧光斑(brand-100 + accent-100,模糊 100px,opacity 0.6),深色模式同样色但 opacity 0.15,缓慢漂移(40s 一个周期的 transform 动画)

中间放一个 **登录卡**:

- 宽度 420px,内边距 40px(垂直)× 32px(水平)
- 圆角 `radius-2xl`(24px)
- 浅色:`background: rgba(255,255,255,0.85); backdrop-filter: blur(20px);` + `shadow-xl` + 1px `rgba(0,0,0,0.04)` 边框
- 深色:`background: rgba(23,26,31,0.7); backdrop-filter: blur(20px);` + `shadow-xl` + 1px `rgba(255,255,255,0.06)` 边框
- 这种"frosted glass"效果是 Linear / Vercel 登录页的标志手法

#### ASCII 草图

```
┌─────────────────────────────────────────────────┐
│                                          [☀/🌙]│
│                                                 │
│                                                 │
│              ╔═══════════════════╗              │
│              ║                   ║              │
│              ║       [Logo]      ║              │
│              ║                   ║              │
│              ║   欢迎回来        ║              │
│              ║   登录到签到管家  ║              │
│              ║                   ║              │
│              ║   用户名          ║              │
│              ║  ┌─────────────┐  ║              │
│              ║  │             │  ║              │
│              ║  └─────────────┘  ║              │
│              ║                   ║              │
│              ║   密码     [忘记?]║              │
│              ║  ┌─────────────┐  ║              │
│              ║  │             │ 👁║              │
│              ║  └─────────────┘  ║              │
│              ║                   ║              │
│              ║  ☐ 30 天免登录    ║              │
│              ║                   ║              │
│              ║  ┌─────────────┐  ║              │
│              ║  │   登 录      │  ║              │
│              ║  └─────────────┘  ║              │
│              ║                   ║              │
│              ║ ─── 安全提示 ───  ║              │
│              ║ 此实例仅限私网部署║              │
│              ╚═══════════════════╝              │
│                                                 │
│              v0.1.0 · 服务端 connected ●       │
└─────────────────────────────────────────────────┘
```

#### 美化要点

- Logo 上方留一个 56×56 的圆角 brand-500 → brand-700 渐变方块,内含产品 icon(白色,Lucide `terminal-square`),增加品牌识别。
- 输入框 focus 时:边框从 neutral-200 渐变到 brand-500,同时加上 `box-shadow: shadow-glow-brand`。过渡 200ms。
- 登录按钮:brand-500 底色,hover 时背景滑入一层 `linear-gradient(180deg, rgba(255,255,255,0.08), transparent)` 让按钮"亮起来";按下时 transform: scale(0.99) + brand-600;loading 时按钮内 spinner 居中并文字淡出为"登录中…"。
- 服务端连接状态点(右下角)是一个呼吸的 success-500 dot(scale 1→1.2→1 循环 2s)。
- 首次访问检测到未初始化 → 自动跳 `/setup` 引导设置管理员密码(同样卡片样式,标题改"创建管理员账户",含"密码""确认密码""可选邮箱(用于密码重置)"三字段)。

### 3.2 仪表盘 `/dashboard`

主体三段:**KPI 区 → 脚本卡片网格 → 最近执行时间线**。整体走"最重要的数据放最上面,可扫读"的原则。

#### ASCII 草图

```
╔══════════════════════════════════════════════════════════════════════════╗
║ 仪表盘                                              [⟳ 刷新]  [+ 扫描]   ║
║ 实时概览,数据每 30s 自动刷新                                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────╮║
║ │ 📦 脚本  │ │ ✅ 成功率│ │ ⚡ 今日  │ │ ⏱  下次  │ │ ❌ 失败  │ │📨 通║║
║ │  12      │ │  96.4%   │ │  148     │ │  03:42    │ │  2       │ │ 23 ║║
║ │ +2 本周  │ │ ▁▂▃▅▆▇▆▅ │ │ ▂▃▅▇█▇▅▃ │ │ 阿里云盘 │ │ -1 vs 昨 │ │ ▅▆ ║║
║ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────╯║
║                                                                          ║
║ 我的脚本                              [全部 12]  [启用 10]  [停用 2]    ║
║                                                                          ║
║ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐             ║
║ │▎🟢 阿里云盘签到 │ │▎🟡 京东签到     │ │▎🔴 V2EX 签到    │             ║
║ │ aliyundrive     │ │ jd-checkin      │ │ v2ex-daily      │             ║
║ │                 │ │                 │ │                 │             ║
║ │ 上次 03:41 ✓    │ │ 上次 06:00 ⚠   │ │ 上次 02:00 ✗    │             ║
║ │ Cron 每天 03:00 │ │ Cron 每天 06:00 │ │ Cron 每天 02:00 │             ║
║ │ 实例 3 个       │ │ 实例 1 个       │ │ 实例 1 个       │             ║
║ │                 │ │                 │ │                 │             ║
║ │ [▶] [⚙] [📜]    │ │ [▶] [⚙] [📜]    │ │ [▶] [⚙] [📜]    │             ║
║ └─────────────────┘ └─────────────────┘ └─────────────────┘             ║
║ ... 更多卡片 ...                                                         ║
║                                                                          ║
║ 最近执行                                              [→ 全部历史]      ║
║ ┌────────────────────────────────────────────────────────────────────┐ ║
║ │ ● 03:41:22  阿里云盘签到 / 主账号        success    1.2s    [详情] │ ║
║ │ ● 03:00:14  阿里云盘签到 / 备账号        success    2.4s    [详情] │ ║
║ │ ● 02:00:03  V2EX 签到                    failure    0.8s    [详情] │ ║
║ │ ● 01:30:00  GitHub Star 备份             success   12.1s    [详情] │ ║
║ │ ... 虚拟滚动,点击展开 stdout/stderr ...                            │ ║
║ └────────────────────────────────────────────────────────────────────┘ ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

#### KPI 卡片设计

`<KpiCard>` 单卡 200×120px(min),`grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`,gap 16px,在 1280px 宽度下大概 4-6 列。

- 卡片背景:浅色 neutral-0,深色 neutral-50;圆角 12px;边框 1px neutral-200(浅)/`rgba(255,255,255,0.06)`(深);阴影 shadow-sm
- hover 时 shadow → shadow-md + translateY(-2px),过渡 200ms
- 内部布局:
  - 左上:24×24 图标(brand-500 或语义色),配合 12×12 图标背景圆 brand-50(浅)/brand-900-alpha(深)
  - 左:标题(text-sm, neutral-500),数字(text-3xl, font-bold, tabular-nums, neutral-900),数字下方 trend(text-xs:`+2 本周`,绿色或红色)
  - 右下:24px 高的 sparkline(用 unovis 或简易 SVG polyline),颜色为本卡的语义色降饱和
- 数字进入时 count-up 动效 800ms

六张 KPI 固定:
1. **总脚本数**(brand)— 含本周新增
2. **今日成功率**(success)— 含 7 日 sparkline
3. **今日执行次数**(info)— 含 24 小时 sparkline
4. **下次执行倒计时**(brand)— 含触发的脚本名,实时倒计时 hh:mm:ss
5. **今日失败数**(danger)— 含与昨日对比
6. **今日通知发送数**(accent)— 含 sparkline

#### 脚本卡片(网格区)

每个脚本一张 `<ScriptCard>`。

- 卡尺寸 min 280px wide × 160px tall,网格 `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`,gap 16px
- 卡片左侧 4px 宽的"状态色条"(success/warning/danger/neutral 对应"上次成功/有警告/上次失败/未运行")
- 顶部:32×32 圆角图标(脚本自带或默认)+ 中文标题(text-lg, 600)+ 下方 slug(text-xs, neutral-500, mono)
- 中间:三行小字(text-sm),`上次 时间 状态icon`、`Cron 表达式`、`实例 N 个`
- 底部:三个 32×32 ghost icon 按钮——`Play`(立即运行)、`Settings`(去配置)、`ScrollText`(看日志)
- hover 时整卡略微抬升 + 状态色条变粗(4px → 5px)

#### 最近执行时间线

虚拟滚动列表,行高 48px,默认显示最近 50 条。

- 每行结构:`● 时间戳(mono, w-100) │ 脚本/实例名 │ 状态 badge │ 时长(mono) │ [详情]按钮`
- 状态点 ● 的颜色对应 success/failure/running(running 时呼吸动画)
- 点击 [详情] 在右侧打开抽屉(含 stdout/stderr)
- 列表上方的"最近执行"小标题右侧有 `→ 全部历史` 链接跳 `/runs`

#### 空状态

如果 `scripts.list.length === 0`:整个仪表盘主体替换为一张大卡:

- 居中插画(unDraw 风 SVG 或 Lottie 装载,主题"empty-folder"),宽度 240px
- 标题"还没有签到脚本"
- 副标题"扫描 `~/scripts` 目录或手动添加你的第一个脚本"
- 主按钮 `[扫描脚本目录]`(brand-500)+ 副按钮 `[查看文档]`(ghost)

### 3.3 脚本列表 `/scripts`

#### ASCII 草图

```
╔══════════════════════════════════════════════════════════════════════════╗
║ 脚本                                                  [⊞ 卡片] [≡ 表格] ║
║ 共 12 个脚本                                                             ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║ ┌────────────────┐ ┌──────────────┐ ┌──────────┐    ┌──────────────┐   ║
║ │🔍 搜索脚本…    │ │ 分类: 全部 ▾ │ │ 状态 ▾   │    │ + 扫描脚本    │   ║
║ └────────────────┘ └──────────────┘ └──────────┘    └──────────────┘   ║
║                                                                          ║
║ — 卡片视图 —                                                             ║
║ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐             ║
║ │ ScriptCard …   │ │ ScriptCard …    │ │ ScriptCard …    │             ║
║ └─────────────────┘ └─────────────────┘ └─────────────────┘             ║
║                                                                          ║
║ — 表格视图 —                                                             ║
║ ┌────────────────────────────────────────────────────────────────────┐ ║
║ │ ☐  名称           分类  实例  Cron        上次  状态  操作         │ ║
║ ├────────────────────────────────────────────────────────────────────┤ ║
║ │ ☐  阿里云盘签到   云盘   3    每天 03:00  03:41  ✅   [▶][⚙][⋯]   │ ║
║ │ ☐  京东签到       购物   1    每天 06:00  06:00  ⚠    [▶][⚙][⋯]   │ ║
║ │ ☐  V2EX 签到      论坛   1    每天 02:00  02:00  ❌   [▶][⚙][⋯]   │ ║
║ └────────────────────────────────────────────────────────────────────┘ ║
║                                                                          ║
║ 选中 0 项                                            [批量启用] [批量禁]║
╚══════════════════════════════════════════════════════════════════════════╝
```

#### 工具栏细节

- **搜索框**:左侧带 `Search` 图标,placeholder "搜索脚本名 / slug",支持模糊匹配(脚本名、slug、tag),200ms debounce。`⌘K` 提示放在右侧浅色快捷键 chip。
- **分类筛选**:Element Plus Select,但要重写样式去掉默认下拉箭头改用 Lucide `chevron-down`,并改下拉菜单的圆角与阴影。
- **状态筛选**:多选 checkbox,在 popover 里(全部/启用/停用/有失败)。
- **视图切换 segmented control**:两个图标按钮(`LayoutGrid` / `List`),被选中的按钮加 brand-50(浅)/brand-900-alpha(深)底色,过渡 200ms,记忆到 localStorage。
- **+ 扫描脚本**:主 CTA,brand-500 实心。点击后弹出 confirm dialog 显示扫描进度(SSE 推送)。

#### 卡片视图

复用仪表盘的 `<ScriptCard>`。

#### 表格视图

- 用 Element Plus `el-table` + 重度自定义 SCSS:
  - 表头:背景 neutral-50(浅)/neutral-100(深),字号 text-xs,字重 600,字色 neutral-500
  - 行高 56px,垂直居中
  - 行间分割:1px 实线 neutral-200(浅)/`rgba(255,255,255,0.04)`(深)
  - hover 整行:背景渐变到 neutral-50,过渡 120ms
  - 选中行:左侧 3px brand-500 色条 + 背景 brand-50
- 复选框列改用自定义样式(圆角 4px,选中时 brand-500 + 白勾)
- 状态列直接用 `<StatusBadge>` 组件

#### 批量操作栏

当 `selected.length > 0` 时,底部从下方滑入一个浮动操作条:

- 高度 56px,position fixed bottom + 居中,宽度 600px,圆角 12px,阴影 lg,backdrop-filter blur 20px
- 左侧:`选中 N 项`,右侧 `[批量启用] [批量禁用] [批量删除]`,danger 用 rose 描边
- 进入动画:translateY(60px) → 0,200ms ease-out

### 3.4 脚本详情 `/scripts/:slug`

#### ASCII 草图

```
╔══════════════════════════════════════════════════════════════════════════╗
║ ← 脚本                                                                  ║
║ ┌──────────────────────────────────────────────────────────────────────┐║
║ │ ┌──┐                                                                  │║
║ │ │📦│ 阿里云盘签到                              [▶ 立即运行]           │║
║ │ └──┘ aliyundrive · v0.3.2 · 已启用 ●            [⏸ 禁用] [↻ 扫描]    │║
║ │       签到阿里云盘并领取每日免费空间                                   │║
║ └──────────────────────────────────────────────────────────────────────┘║
║                                                                          ║
║ [概览] [实例 (3)] [配置模板] [执行历史] [实时日志] [README]              ║
║ ════════                                                                 ║
║                                                                          ║
║ — 概览 tab —                                                             ║
║ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐             ║
║ │ 30 日成功率      │ │ 30 日执行次数    │ │ 平均耗时         │             ║
║ │ 98.2%            │ │ 90               │ │ 1.4s             │             ║
║ │ ▆▇▆█▇▆▇▆▇█      │ │ ▃▂▃▂▃▂▃▂▃▂      │ │ ━━━ ▁▂▁▂▁▂      │             ║
║ └─────────────────┘ └─────────────────┘ └─────────────────┘             ║
║                                                                          ║
║ 调度信息                                                                 ║
║ ┌──────────────────────────────────────────────────────────────────────┐║
║ │ Cron     0 3 * * *                  下次执行  约 23 小时 14 分后     │║
║ │ 时区     Asia/Shanghai              超时       5 分钟                │║
║ │ 重试     失败重试 2 次,间隔 60s    锁         单实例锁              │║
║ └──────────────────────────────────────────────────────────────────────┘║
║                                                                          ║
║ 实例摘要                                                  [→ 全部 (3)] ║
║ ┌──────────────────────────────────────────────────────────────────────┐║
║ │ 主账号        ●启用    上次 03:41 ✓                       [▶][⚙]    │║
║ │ 备账号        ●启用    上次 03:00 ✓                       [▶][⚙]    │║
║ │ 测试账号     ○停用    上次 ——                            [▶][⚙]    │║
║ └──────────────────────────────────────────────────────────────────────┘║
╚══════════════════════════════════════════════════════════════════════════╝
```

#### 顶部 PageHeader

`<PageHeader>` 通用组件,含面包屑 `脚本 / 阿里云盘签到` + 主标题区:

- 左:48×48 脚本图标(脚本元数据中提供 url 或本地 SVG,无则用 Lucide `package` 默认),圆角 12px,自带浅色边框
- 中:脚本中文名(text-2xl)+ slug(text-sm mono neutral-500)+ 启用状态点(success-500 / neutral-400)+ 描述(text-base neutral-600)
- 右:操作按钮组——`[▶ 立即运行]` brand-500 主按钮 + `[⏸ 禁用 / ▶ 启用]` ghost + `[↻ 扫描更新]` ghost + 更多菜单 `⋯`(含"删除脚本""导出配置")

整个 header 用一张大卡(neutral-0 底,圆角 lg,边框,padding 24px)。下方是 tabs。

#### Tabs

Element Plus `el-tabs` 重写样式:

- 横向排列,左对齐
- 默认 tab 字色 neutral-500;hover 字色 neutral-700;active 字色 brand-600 + 下方 2px brand-500 indicator
- indicator 在切换时滑动(transform translateX),200ms ease-out
- 移除 Element Plus 默认的灰色 tab-pane 边框

#### 概览 tab

- 三张统计卡:30 日成功率 / 30 日执行次数 / 平均耗时(同 KPI 卡样式但稍小,160px 高)
- 调度信息卡:`<DescriptionList>` 风格,2 列,key 用 neutral-500,value 用 neutral-800
- 实例摘要列表(同表格视图行样式,小尺寸)

#### 实例 tab

实例列表表格 + 顶部 `[+ 创建实例]` 按钮。点击实例行进入实例详情,或行内 `[⚙]` 按钮直接打开右侧配置抽屉。

#### 配置模板 tab

显示该脚本的 `fields_schema`(只读视图,有点像 GraphQL Playground 的 schema panel),让用户了解每个实例可配什么字段:

- 字段名(mono)+ 类型 badge + required 标记 + 描述 + 默认值 + 校验规则
- 支持复制 JSON schema

#### 执行历史 tab

复用 `<RunListTable>` 组件,默认筛选 `script_slug = current`。

#### 实时日志 tab

详见 3.7。

#### README tab

- 渲染脚本目录中的 `README.md`(后端返回 raw markdown)
- 用 `marked` + `highlight.js` 渲染,代码块用我们的字体和深浅主题
- 最大宽度 720px 居中,提升可读性

### 3.5 实例配置表单(抽屉)

打开方式:从脚本详情 `[+ 创建实例]` 或实例行的 `[⚙]` 按钮触发,从右侧滑入。宽度 560px(可配置 480-800),全屏高度。

#### ASCII 草图

```
╔════════════════════════════════════════════════╗
║ 实例配置 — 阿里云盘签到 / 主账号        [×]   ║
║ 编辑后点击右下方"保存"生效                     ║
╠════════════════════════════════════════════════╣
║                                                ║
║ ▾ 基本                                         ║
║   实例名 *                                     ║
║   ┌────────────────────────────────────────┐  ║
║   │ 主账号                                 │  ║
║   └────────────────────────────────────────┘  ║
║                                                ║
║   备注                                         ║
║   ┌────────────────────────────────────────┐  ║
║   │                                        │  ║
║   └────────────────────────────────────────┘  ║
║                                                ║
║ ▾ 鉴权                                         ║
║   refresh_token *  ⓘ 用于刷新登录态           ║
║   ┌────────────────────────────────────────┐  ║
║   │ ••••••••••••••••••••••••  👁  📋        │  ║
║   └────────────────────────────────────────┘  ║
║                                                ║
║   device_id   ⓘ 可选,留空自动生成             ║
║   ┌────────────────────────────────────────┐  ║
║   │                                        │  ║
║   └────────────────────────────────────────┘  ║
║                                                ║
║ ▾ 调度                                         ║
║   Cron 表达式                                  ║
║   ┌────────────────────────────────────────┐  ║
║   │ 0 3 * * *                              │  ║
║   └────────────────────────────────────────┘  ║
║   下次执行 · 2026-05-16 03:00:00 (CST)         ║
║   人话翻译 · 每天 03:00                        ║
║                                                ║
║   超时(秒)                                  ║
║   ┌──────────┐                                 ║
║   │   300 ⇅  │                                 ║
║   └──────────┘                                 ║
║                                                ║
║   启用                                         ║
║   ●━━━○                                       ║
║                                                ║
║ ▾ 通知                                         ║
║   通知渠道(可多选)                          ║
║   [Telegram-我] [Bark-iPhone] [+ 新增]        ║
║                                                ║
╠════════════════════════════════════════════════╣
║ [测试运行]                  [取消]  [保 存]    ║
╚════════════════════════════════════════════════╝
```

#### 字段类型映射

后端返回的 `fields_schema` 结构形如:

```
[
  { key: "refresh_token", type: "secret", label: "refresh_token", required: true, description: "...", group: "鉴权" },
  { key: "cron", type: "cron", label: "Cron 表达式", default: "0 3 * * *", group: "调度" },
  ...
]
```

前端按 `group` 分块渲染折叠面板;每字段按 `type` 选组件:

| type | 组件 | 行为细节 |
|---|---|---|
| `string` | `<el-input>` 重写样式 | min-height 38px,圆角 8px,focus 时 brand-500 边框 + glow |
| `secret` | `<SecretInput>` | 默认密文,右侧带"显隐"和"复制"按钮;复制时 toast 提示 |
| `integer` | `<el-input-number>` 重写样式 | 上下箭头改用 Lucide `chevron-up/down`,放在右侧竖排 |
| `boolean` | `<el-switch>` 重写样式 | 32×18 滑块,active brand-500,带 spring easing |
| `select` | `<el-select>` 重写样式 | popover 下拉自带 8px 圆角 + shadow-lg |
| `multiselect` | `<el-select multiple>` | 选中项用 chip 样式,每个 chip 带 ✕ |
| `multiline` | `<el-input type="textarea">` | min-rows 3,max-rows 12,resize-y |
| `cron` | `<CronInput>` | 详见 4.4 |
| `url` | `<el-input>` + url validator | 输入时实时校验,失败 shake 动画 |
| `json` | `<MonacoEditor>`(轻量 monaco 或 codemirror) | 100-300px 高,语法高亮 |
| `enum_radio` | `<el-radio-group>` 重写样式 | 卡片式 radio(每个 option 是带 icon 的小卡) |

#### 表单分组

每组用 `<CollapsibleSection>`:

- 默认展开
- 标题左侧 `chevron-right` 图标,展开时 90° 旋转(transition 200ms)
- 标题字号 text-sm,字重 600,字色 neutral-700
- 字段间垂直 space-4(16px)

#### 字段说明 tooltip

label 后跟一个 12×12 `info` 图标(neutral-400),hover 触发 popover:

- 圆角 8px,阴影 lg,padding 12px,max-width 280px
- 200ms fade-in,延迟 300ms 出现
- 内容:字段说明 + 示例值(mono 字体高亮)

#### 错误提示

- 字段下方 4px 间距显示 `<FieldError>`(text-xs danger-500),配合左侧 `alert-circle` 图标
- 错误时 input 边框变 danger-500
- 保存时若后端返回字段级错误,自动定位并 scroll 到第一个错误字段

#### 保存动效

按"乐观更新"策略:

- 点击 `[保 存]` 按钮:按钮立即变 loading 状态(spinner + "保存中…"),200ms 后请求出去
- 成功:按钮变 success-500 + ✓ 文案"已保存",1s 后还原;同时抽屉自动关闭(可关闭/可保留,默认关闭),并 toast 右上"已保存 主账号"
- 失败:按钮还原 + danger toast + 字段级错误高亮

#### 测试运行

抽屉左下角的 `[测试运行]` 按钮:

- 点击后切换到底部内嵌一个迷你日志面板(高度 240px,可拖动),实时 SSE 显示 stdout/stderr
- 不会保存配置,只用当前表单值跑一次(调用 `/api/scripts/{slug}/test-run` POST 当前表单)
- 完成后底部显示 `✓ 成功 1.2s` 或 `✗ 失败 — exit 1`

### 3.6 执行历史 + 详情

#### 列表 `/runs`

- 顶部工具栏:搜索(按脚本/实例)、状态多选筛选、时间范围选择(快捷:今日/昨日/7日/30日/自定义)、`[导出 CSV]`
- 表格虚拟滚动(用 `vue-virtual-scroller`),默认每页 100,滚动到底自动加载下一页
- 列:`时间(mono)`、`脚本/实例`、`状态 badge`、`耗时(mono)`、`触发方式 chip(cron / manual / api)`、`操作 [详情]`
- 状态色条:每行左侧 3px,success/failure/running

#### 详情抽屉

点击行打开右侧抽屉(宽 720px):

```
╔══════════════════════════════════════════════════════════╗
║ 执行详情 #cf83b2                                  [×]    ║
║ 阿里云盘签到 / 主账号 · 2026-05-15 03:41:22       [复制] ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    ║
║ │ 状态     │ │ 耗时     │ │ exit     │ │ 触发     │    ║
║ │ ✅ 成功  │ │ 1.234s   │ │ 0        │ │ Cron     │    ║
║ └──────────┘ └──────────┘ └──────────┘ └──────────┘    ║
║                                                          ║
║ 元信息                                                   ║
║   开始时间   2026-05-15 03:41:22.103                     ║
║   结束时间   2026-05-15 03:41:23.337                     ║
║   节点       worker-1                                    ║
║   进程 PID   28714                                       ║
║                                                          ║
║ ▾ stdout (24 行)                                  [📋]   ║
║ ┌──────────────────────────────────────────────────────┐ ║
║ │ 1  [INFO] 启动签到流程…                              │ ║
║ │ 2  [INFO] 加载配置 主账号                            │ ║
║ │ 3  [INFO] 刷新 access_token 成功                     │ ║
║ │ ...                                                   │ ║
║ │ 24 [INFO] 签到完成,获得 1024MB                      │ ║
║ └──────────────────────────────────────────────────────┘ ║
║                                                          ║
║ ▾ stderr (0 行)                                          ║
║   (无输出)                                               ║
║                                                          ║
║ 通知                                                     ║
║   ✓ Telegram-我   已发送  03:41:23                      ║
╚══════════════════════════════════════════════════════════╝
```

stdout/stderr 用 `<LogViewer>` 内嵌(精简版),支持复制全文、搜索高亮。失败时 stderr 自动展开。

### 3.7 实时日志(SSE) `/scripts/:slug?tab=logs`

#### 视觉

整个面板做成"嵌入式终端"风格,但不要纯粹复刻 macOS Terminal,要有现代感:

- 容器高度 `calc(100vh - 200px)`,圆角 lg,边框,内部背景 `#0E1116`(浅色模式下)/`#0B0D10`(深色模式下原生)
- 顶部工具条 40px:左侧脚本名 + 实例下拉切换 + 连接状态点(green pulse 表示 SSE 连接中)
- 右侧工具按钮:`[⏸ 暂停 / ▶ 恢复]`、`[↓ 跟随到底部]`(active 时填充 brand-500)、`[🔍 搜索]`、`[⏷ 折行]`、`[⛶ 全屏]`、`[🗑 清屏]`、`[📋 复制]`、`[💾 下载]`
- 主体内容区:
  - 字体 JetBrains Mono 13px,line-height 20px
  - 行结构:`[12.5 chars 时间]  [4 chars 行号]  [日志正文]`
  - 时间戳 neutral-500,行号 neutral-600,正文 neutral-100
  - ANSI 颜色用 `ansi_up` 解析为 span,语义色映射到我们的 success/warning/danger/info 500
  - 行 hover 时整行 background `rgba(255,255,255,0.03)`
  - 选中范围背景 brand-500 alpha 0.2

#### 交互

- 自动滚动到底部:默认开启,用户向上滚 → 自动暂停跟随,顶部显示一个浮动 toast "已暂停跟随,点此回到底部"
- 暂停按钮:停止接收新日志(SSE 连接保持,客户端缓冲超过 5000 行后丢弃最旧)
- 搜索:`⌘F` 触发顶部搜索条,实时高亮匹配项,按 `Enter` 跳到下一个
- 高亮:支持正则模式切换
- 全屏:整个 LogViewer 占满 viewport,topbar/sidebar 隐藏
- 行号点击:复制单行
- 单行右键:菜单"复制""复制行号""高亮该正则模式"

#### SSE 状态指示

- 连接中:右上角 pulse green dot
- 重连中:pulse warning dot + tooltip "重连中(尝试 3/∞)"
- 断开:gray dot + tooltip "已断开,点击重连"
- 出错:danger dot + 顶部红色 banner

### 3.8 通知渠道 + 规则页 `/notifications`

两个 tab:**渠道** 和 **规则**。

#### 渠道 tab

```
╔══════════════════════════════════════════════════════════════════════════╗
║ 通知                                                                     ║
║ [渠道] [规则]                                          [+ 新增渠道]     ║
║ ═══                                                                      ║
║ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐         ║
║ │ 📱 Telegram-我   │ │ 🔔 Bark-iPhone   │ │ ✉ 邮箱-备份      │         ║
║ │ Telegram         │ │ Bark             │ │ SMTP             │         ║
║ │                  │ │                  │ │                  │         ║
║ │ ●启用 · 已发 23  │ │ ●启用 · 已发 18  │ │ ○停用            │         ║
║ │ 上次成功 03:41   │ │ 上次成功 03:41   │ │ 上次 ——          │         ║
║ │                  │ │                  │ │                  │         ║
║ │ [测试] [⚙] [删]  │ │ [测试] [⚙] [删]  │ │ [测试] [⚙] [删]  │         ║
║ └──────────────────┘ └──────────────────┘ └──────────────────┘         ║
║ ...                                                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
```

- 每张渠道卡尺寸 320×180px
- 图标:Telegram、Bark、邮箱、Slack、企业微信、钉钉、Webhook 等,各自有特色色彩(Telegram 蓝、Bark 黑、邮箱灰)
- `[测试]` 按钮:点击后立即发送一条测试消息,按钮转 loading,成功后 success toast "测试消息已送达"
- `[⚙]` 编辑配置(右侧抽屉,字段动态生成同 3.5)
- 新增渠道:点击 `[+ 新增渠道]` 弹出选择类型卡片网格(图标 + 名称),选择后进入配置抽屉

#### 规则 tab

矩阵视图:**脚本(行)× 触发条件(列)× 渠道(单元格)**。

```
╔══════════════════════════════════════════════════════════════════════════╗
║ 规则                                                  [+ 新增规则]      ║
║                                                                          ║
║ ┌─────────────────┬──────────┬──────────┬──────────┬──────────┐         ║
║ │ 脚本/实例 \触发 │  成功    │  失败    │  超时    │  连续失败│         ║
║ ├─────────────────┼──────────┼──────────┼──────────┼──────────┤         ║
║ │ 阿里云盘签到    │  ——      │ TG · Bark│ TG       │ TG · 邮  │         ║
║ │ 京东签到        │ ——       │ TG       │ TG       │ TG · 邮  │         ║
║ │ V2EX 签到       │ ——       │ TG       │ ——       │ TG       │         ║
║ │ 全局兜底        │ ——       │ TG       │ TG       │ 邮       │         ║
║ └─────────────────┴──────────┴──────────┴──────────┴──────────┘         ║
║                                                                          ║
║ 单元格点击 → 弹出 popover 多选渠道                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
```

- 单元格内显示已绑定渠道的 chip,空时显示淡淡的 `+`
- 点击单元格弹 popover:渠道复选框列表 + `[保存]`
- 行末 `[⋯]` 菜单:删除规则、复制规则
- 顶部 `[+ 新增规则]`:抽屉表单,选脚本(可选实例)+ 选触发条件 + 选渠道
- "全局兜底":一行特殊 highlight,适用于所有未匹配脚本

### 3.9 设置页 `/settings`

垂直 tab 布局(左侧 tab 列表 200px,右侧内容区)。

#### Tab 列表

```
账户
外观
备份
关于
```

#### 账户 tab

- 修改密码(当前密码 / 新密码 / 确认新密码)
- 修改用户名
- API Token(显示已生成的 token + 重新生成按钮 + 撤销)
- 双因素认证(TOTP)预留(toggle)

#### 外观 tab

```
╔══════════════════════════════════════════════════════════╗
║ 外观                                                     ║
║                                                          ║
║ 主题                                                     ║
║ ┌─────────┐ ┌─────────┐ ┌─────────┐                    ║
║ │ 浅色    │ │ 深色 ●  │ │ 跟随系统│                    ║
║ │ ☀       │ │ 🌙      │ │ ⚙       │                    ║
║ └─────────┘ └─────────┘ └─────────┘                    ║
║                                                          ║
║ 主题色                                                   ║
║ ⬤ ⬤ ⬤ ⬤ ⬤ ⬤ ⬤   ●自定义                       ║
║ Indigo Blue Teal Rose Amber Violet Stone                 ║
║                                                          ║
║ 字号                                                     ║
║ ●━━━━━○━━━━━○                                          ║
║ 紧凑   标准   宽松                                      ║
║                                                          ║
║ 圆角                                                     ║
║ 微圆 ━━●━━━ 大圆                                       ║
║                                                          ║
║ 动效                                                     ║
║ ●━━○ 启用                                              ║
║ ○━━━ 减少动画(Reduced Motion)                          ║
║                                                          ║
║ 高级                                                     ║
║ □ 边栏默认折叠                                          ║
║ □ 表格默认紧凑模式                                      ║
║ □ 启用实验性图表                                        ║
╚══════════════════════════════════════════════════════════╝
```

主题切换实时生效(无需保存),写入 localStorage + 同步到后端 user_preferences。

#### 备份 tab

- 自动备份开关 + 频率(每天/每周)+ 保留份数
- 手动备份按钮 → 生成 zip 下载
- 恢复:上传 zip + 校验 + 应用
- 备份列表(时间、大小、动作)

#### 关于 tab

- 产品名 / 版本 / 构建时间 / Git commit
- 后端版本(从 `/api/health` 拉)
- 系统信息(Python 版本、Node 版本、OS、磁盘占用)
- 开源协议、致谢、链接 GitHub

### 3.10 全局组件

#### 顶栏 Topbar

高度 56px,固定,贯穿整个 AppLayout。

```
╔══════════════════════════════════════════════════════════════════════════╗
║ ☰ [Logo] 签到管家   ⌘K 搜索…              [⌘B] [☀/🌙] [🔔3] [Avatar ▾] ║
╚══════════════════════════════════════════════════════════════════════════╝
```

- 左:折叠按钮(`PanelLeftClose` / `PanelLeftOpen`),logo+产品名(浅色模式 brand-700,深色模式 neutral-900)
- 中:全局搜索触发器,640px 宽,样式像一个输入框但点击后弹出 ⌘K 命令面板。右侧 ⌘K 快捷键 chip。
- 右:键盘快捷键提示(? icon)、主题切换(`Sun`/`Moon` 图标,toggle 时有 30° 旋转动画)、通知中心(`Bell`,带未读 dot)、用户头像下拉(账户、设置、退出)

#### 侧边栏 Sidebar

宽度 240px(展开)/ 64px(折叠),可记忆。

```
╔════════════════════╗
║                    ║
║ ⊞ 仪表盘          ║
║ ▣ 脚本            ║
║   • 阿里云盘签到   ║
║   • 京东签到       ║
║ 📜 执行历史       ║
║ 🔔 通知           ║
║ ⚙ 设置            ║
║                    ║
║ ─────────          ║
║                    ║
║ 系统状态           ║
║ ●运行中           ║
║ 12 脚本 · 3 实例  ║
║                    ║
╚════════════════════╝
```

- 每项高度 40px,圆角 8px,padding-x 12px
- 默认 hover:背景 neutral-100(浅)/neutral-200(深)
- active:背景 brand-50(浅)/brand-900-alpha(深)+ 字色 brand-700 / brand-400 + 左侧 3px brand-500 indicator(圆角)
- 图标 18×18(Lucide),与文字间距 space-3
- 折叠态:仅显示图标居中,hover 时显示 tooltip(右侧浮窗)
- "脚本"项可展开二级列表(显示已启用脚本的快捷链接,最多 5 个 + 更多)
- 底部固定区:系统状态卡(连接状态点 + 数量)+ 版本号(text-xs neutral-500)

#### 全局通知 toast

- 位置 right: 24px, top: 80px(避开顶栏)
- 单个 toast 宽 360px,圆角 12px,阴影 lg
- 结构:左 4px 语义色条 + 图标(success/warning/danger/info)+ 标题(text-sm 600)+ 描述(text-sm)+ 关闭 X
- 进入:translateX(100%) → 0,duration 320ms,easing-decelerate
- 自动消失:默认 4s(可配),hover 时停止计时,鼠标移开继续
- 多个 toast 垂直堆叠,gap 12px,新进入的从上方插入并把旧的下推

#### 全局命令面板(⌘K)

参考 Raycast / VS Code 命令面板。`⌘K` / `Ctrl+K` 触发,点击顶栏搜索框也触发。

- 居中对话框,宽 640px,top: 15vh,圆角 12px,阴影 xl,backdrop-filter blur 24px,半透明背景
- 顶部输入框(无边框,大字,placeholder "搜索脚本、命令、设置…")
- 下方分组结果列表:
  - **脚本**:阿里云盘签到 / 京东签到 …
  - **导航**:仪表盘 / 通知 / 设置 …
  - **操作**:立即运行 [脚本名] / 切换主题 / 查看日志…
  - **最近**:最近访问的页面
- 键盘:↑↓ 导航,Enter 执行,Esc 关闭
- 模糊匹配:fuse.js,关键字高亮 brand-500
- 进入动画:scale(0.96) → 1 + opacity 0 → 1,duration 200ms

### 3.11 状态设计

#### 空状态 EmptyState 组件

每个列表/网格在数据为空时显示。统一结构:

- 居中,垂直 padding 80px
- 顶部 SVG 插画(120-200px 宽,降饱和度 80% 让它和谐)或大号 Lucide icon(64px,neutral-400)
- 标题(text-xl,neutral-700,padding-top 24px)
- 副标题/说明(text-base,neutral-500,max-width 320px)
- 主操作按钮(brand-500)+ 可选副操作(ghost"查看文档")

各页面的空状态:

- 仪表盘 → "还没有签到脚本"
- 脚本列表 → "尚未发现脚本",CTA "扫描 ~/scripts" + "查看脚本结构示例"
- 实例列表 → "该脚本还没有实例",CTA "创建第一个实例"
- 执行历史 → "没有执行记录",CTA "运行任意脚本"
- 通知渠道 → "没有配置通知渠道",CTA "新增渠道"
- 通知规则 → "没有配置通知规则",CTA "新增规则"

#### 错误状态

- **API 失败**(单个组件):整个组件区域替换为 inline error,中等大小,Lucide `cloud-off` 图标 + 标题"加载失败" + 描述(error message)+ `[重试]` 按钮
- **网络断开**(全局):页面顶部从下方滑入 banner,danger-50 底,danger-700 字,内容"已与服务器断开连接,自动重连中…",右侧手动重连按钮
- **404**:全屏插画式错误页,大数字 "404"(text-4xl×2,brand-500 → accent-500 渐变文字),"页面去喝奶茶了" + `[回首页]` 按钮
- **500**:类似 404,大数字 "500" + "服务器小哥正在抢救" + `[重试] [回首页] [复制错误信息]`
- **ErrorBoundary**(组件级):捕获子组件渲染异常,fallback 显示 "组件渲染失败" + 错误堆栈折叠 + `[刷新]`

#### Loading

**全部使用 Skeleton 而非 spinner**。

- Skeleton 卡片:同形状的灰块,内部模拟内容布局(标题灰条、文字灰条、按钮灰块)
- 颜色:浅色 neutral-200 → neutral-100 渐变,深色 neutral-200 → neutral-300 渐变
- 动画:`animation: shimmer 1.6s linear infinite`,从左到右的微弱光带
- 例外:小型按钮 loading 用 spinner(Lucide `loader-2`,旋转 1s linear infinite)

每个页面要预先定义对应的 skeleton:

- 仪表盘:6 KPI 卡 + 9 ScriptCard 灰块 + 时间线 10 行
- 脚本列表(卡片):12 ScriptCard 灰块
- 脚本列表(表格):表头 + 10 行灰条
- 脚本详情:header + tabs + 内容区灰块
- 日志:24 行灰条(随机宽度 30-90%)

---

## 4. 公共组件清单

设计层面定义 props 与用途,实现层在编码阶段定结构。

### 4.1 `<StatusBadge>`

- props: `status: 'success' | 'failure' | 'running' | 'pending' | 'disabled' | 'warning'`,`size?: 'sm' | 'md'`,`label?: string`,`pulse?: boolean`
- 视觉:圆角 full,padding 2px 8px,左侧 6px 圆点 + 文字
- 颜色映射:
  - success → success-500 dot + success-700 文字 + success-50 底(浅)
  - failure → danger-500 dot + danger-700 文字 + danger-50 底
  - running → info-500 dot + info-700 文字 + info-50 底,dot 呼吸
  - pending → neutral-400 dot + neutral-600 文字 + neutral-100 底
  - disabled → neutral-300 dot + neutral-500 文字 + neutral-100 底
  - warning → warning-500 dot + warning-700 文字 + warning-50 底
- pulse 时 dot 添加呼吸动画(scale 1→1.2→1 + opacity 1→0.6→1, 2s)

### 4.2 `<ScriptCard>`

- props: `script: Script`,`compact?: boolean`,`onAction?: (action: 'run' | 'config' | 'logs') => void`
- 用途:仪表盘和脚本列表卡片视图
- 已在 3.2 详细描述

### 4.3 `<KpiCard>`

- props: `title: string`,`value: number | string`,`unit?: string`,`icon?: Component`,`tone?: 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'neutral'`,`trend?: { delta: number, label: string }`,`sparkline?: number[]`,`countUp?: boolean`,`loading?: boolean`
- 用途:仪表盘 KPI 区
- 数字进入用 count-up 动画(支持小数、百分号、单位前后缀)

### 4.4 `<CronInput>`

- props: `modelValue: string`,`timezone?: string`,`showPreview?: boolean`,`presets?: { label: string, value: string }[]`
- 视觉:
  - 上方输入框(mono 字体)+ 右侧"预设"按钮(下拉:每天 / 每小时 / 工作日早 9 点 / 自定义)
  - 实时校验,失败 inline error
  - 下方两行预览:
    - `下次执行 · 2026-05-16 03:00:00 (CST)`(用 cronstrue + cron-parser 计算)
    - `人话翻译 · 每天 03:00`(用 cronstrue 中文)
  - 可视化时间线(可选,默认隐藏):未来 10 次执行的时间点
- 错误:无效表达式时下方红色提示"无效的 cron 表达式,请检查"

### 4.5 `<SecretInput>`

- props: `modelValue: string`,`placeholder?: string`,`canCopy?: boolean = true`,`canReveal?: boolean = true`
- 视觉:输入框默认 type="password",右侧两个图标按钮:`Eye` / `EyeOff` 切换,`Copy` 复制
- 复制时:按钮变 success-500 + ✓ 图标 1.5s 后还原,toast "已复制到剪贴板"
- 显隐切换时:输入框内容用 200ms 淡出再淡入(避免直接闪)
- 安全提示:value.length > 0 但全部为 `*` 时显示标签"已加密存储,显示后请勿截图"

### 4.6 `<LogViewer>`

- props: `source: 'sse' | 'static'`,`url?: string`,`content?: string`,`autoScroll?: boolean = true`,`fullscreenable?: boolean = true`,`searchable?: boolean = true`,`maxLines?: number = 5000`,`onConnectionChange?: (state) => void`
- 详见 3.7
- 内部用虚拟滚动(`vue-virtual-scroller`)以支持万行级日志
- ANSI 解析用 `ansi_up`,链接自动识别可点击
- 暴露方法:`scrollToBottom()`, `clear()`, `pause()`, `resume()`

### 4.7 `<EmptyState>`

- props: `icon?: Component`,`illustration?: string`,`title: string`,`description?: string`,`primaryAction?: { label: string, onClick: () => void }`,`secondaryAction?: { label: string, onClick: () => void }`
- 详见 3.11

### 4.8 `<ErrorBoundary>`

- props: `fallback?: Component`,`onError?: (err) => void`
- 用 Vue 3 `errorCaptured` 钩子捕获子组件错误
- 默认 fallback:卡片 + `frown` 图标 + "组件渲染失败" + 折叠堆栈 + `[刷新]` 按钮
- 上报错误到后端 `/api/errors` 用于诊断

### 4.9 `<PageHeader>`

- props: `title: string`,`subtitle?: string`,`breadcrumb?: { label: string, to?: string }[]`,`icon?: Component`,`status?: StatusType`,`actions?: VNode | VNode[]`
- 详见 3.4 顶部
- 在所有 AppLayout 页面顶部使用,统一视觉

### 4.10 `<ConfirmDialog>`

- props: `visible: boolean`,`title: string`,`description?: string`,`type?: 'info' | 'warning' | 'danger'`,`confirmText?: string = '确认'`,`cancelText?: string = '取消'`,`requireTyping?: string`(高危操作要求输入特定文本才能确认)
- 视觉:Modal 居中,420px 宽,圆角 lg,padding 32px,顶部对应 type 的彩色图标圈 64px
- danger 类型:确认按钮 danger-500
- requireTyping:输入框监听,只有匹配后才启用确认按钮(用于"删除脚本""撤销 token"等)

### 4.11 其他辅助组件

- `<DescriptionList>` — 键值对展示(上面用过)
- `<CollapsibleSection>` — 可折叠分组
- `<FieldError>` — 表单字段错误
- `<TrendIndicator>` — 趋势小标(↑3.2% / ↓1.1%)
- `<MiniSparkline>` — 24px 高的迷你折线
- `<CopyButton>` — 复制图标按钮(含成功反馈)
- `<RelativeTime>` — 相对时间("3 分钟前"),hover 显示绝对时间 tooltip,自动每分钟刷新
- `<UserAvatar>` — 用户头像(大写首字母 + brand 渐变背景作 fallback)
- `<KbdShortcut>` — 键盘快捷键 chip 样式(`⌘K`、`Esc` 等)

---

## 5. 状态管理(Pinia stores)

每个 store 一个文件,Composition API 写法,所有 store 必须导出 typed `useXxxStore()`。

### 5.1 `useAuthStore`

- state: `token`(localStorage 同步)、`user`(id, username, email, avatarUrl)、`isLoading`
- actions: `login(username, password, remember)`、`logout()`、`fetchMe()`、`changePassword(...)`、`getApiToken()`、`regenerateApiToken()`
- getters: `isLoggedIn`、`displayName`

### 5.2 `useScriptsStore`

- state: `list: Script[]`、`current: Script | null`、`loading`、`scanning`、`scanProgress`(SSE 推送进度)
- actions: `fetchList()`、`fetchOne(slug)`、`scan()`(触发后端扫描,SSE 监听进度)、`enable(slug)`、`disable(slug)`、`runOnce(slug, instanceId)`、`delete(slug)`
- getters: `enabledList`、`groupedByCategory`、`stats`(脚本数、启用数、停用数)

### 5.3 `useInstancesStore`

- state: `byScript: Record<slug, Instance[]>`、`current: Instance | null`、`loading`、`saving`
- actions: `fetchByScript(slug)`、`fetchOne(scriptSlug, id)`、`create(scriptSlug, data)`、`update(scriptSlug, id, data)`、`delete(scriptSlug, id)`、`testRun(scriptSlug, formData)`(返回 SSE 流)
- getters: `instancesOf(slug)`

### 5.4 `useRunsStore`

- state: `list: Run[]`、`filters`(脚bucket/状态/时间)、`pagination`、`current`、`loading`、`hasMore`
- actions: `fetchList(filters?)`、`fetchOne(id)`、`fetchNextPage()`、`subscribeLive(scriptSlug?)` (SSE)、`unsubscribeLive()`
- getters: `groupedByDay`、`successRate`(根据当前 list 统计)

### 5.5 `useNotificationsStore`

- state: `channels: Channel[]`、`rules: Rule[]`、`loading`
- actions: `fetchChannels()`、`createChannel(type, config)`、`updateChannel(id, config)`、`deleteChannel(id)`、`testChannel(id)`、`fetchRules()`、`saveRule(rule)`、`deleteRule(id)`
- getters: `enabledChannels`、`channelById(id)`、`rulesForScript(slug)`

### 5.6 `useSettingsStore`

- state: `account`、`backup`、`about`(产品/系统信息)
- actions: `fetchSettings()`、`updateAccount()`、`createBackup()`、`restoreBackup(file)`、`listBackups()`、`deleteBackup(id)`、`fetchSystemInfo()`

### 5.7 `useUiStore`

- state:
  - `theme: 'light' | 'dark' | 'system'`(localStorage 同步)
  - `accentColor: AccentColorKey`
  - `sidebarCollapsed: boolean`
  - `density: 'compact' | 'normal' | 'comfortable'`
  - `radius: 'small' | 'medium' | 'large'`
  - `reducedMotion: boolean`
  - `cmdkOpen: boolean`
  - `globalToasts: Toast[]`
- actions: `setTheme()`、`toggleTheme()`、`toggleSidebar()`、`setAccent()`、`pushToast(toast)`、`dismissToast(id)`、`openCmdK()`、`closeCmdK()`、`syncSystemTheme()`(监听 prefers-color-scheme)

### 5.8 持久化策略

- `auth.token`、`ui.*` 字段写 localStorage(用 `pinia-plugin-persistedstate`)
- 其他 store 不持久化(刷新重新拉)

---

## 6. API 封装层

### 6.1 axios 实例

`src/api/http.ts` 暴露唯一 axios 实例:

- `baseURL`:从 `import.meta.env.VITE_API_BASE`(默认 `/api`)
- `timeout`:15s(SSE 不走这里)
- `withCredentials`:true(若用 cookie 模式)
- 请求拦截器:
  - 自动塞 `Authorization: Bearer {token}`(从 useAuthStore)
  - 加上 `X-Client-Version: ${import.meta.env.VITE_APP_VERSION}` 便于排错
  - 加上 `X-Request-Id: nanoid()` 用于追踪
- 响应拦截器:
  - 200/204 直接 return data
  - 401 → 触发 logout + 跳 `/login?redirect=...` + toast "登录已过期"
  - 403 → toast "没有权限"
  - 4xx → 解析后端 `{ code, message, fields }` 结构,抛 `ApiError`(供组件 try/catch 显示字段错误)
  - 5xx → toast "服务器开小差了 (HTTP 500)" + 上报到 errorStore
  - 网络错误 → toast "网络异常,请检查连接"
  - 取消错误(AbortController)→ silent,不 toast

### 6.2 API 方法组织

`src/api/` 按资源拆分:

- `auth.ts`:`login()`, `logout()`, `me()`, `setupStatus()`, `setup()`
- `scripts.ts`:`list()`, `get(slug)`, `scan()`, `runOnce(slug, id?)`, `enable(slug)`, `disable(slug)`, `delete(slug)`
- `instances.ts`:`listByScript(slug)`, `get(slug, id)`, `create()`, `update()`, `delete()`, `testRun()`
- `runs.ts`:`list(params)`, `get(id)`, `cancel(id)`
- `notifications.ts`:渠道 + 规则
- `settings.ts`:账户、备份、系统信息

每个方法返回 `Promise<TypedData>`,类型来自 `src/types/api.ts`(由 OpenAPI 生成)。

### 6.3 SSE 客户端封装

`src/api/sse.ts`,基于原生 `EventSource` 包装,因为它不支持自定义 header。两种方案:

- 方案 A(推荐):用 `@microsoft/fetch-event-source`,支持 fetch + headers + POST + 自动重连
- 方案 B:用 EventSource + 把 token 放 query

封装暴露:

```
class SSEClient {
  constructor(url, options: { token?, body?, retryDelay = 1000, maxRetries = Infinity })
  on(event: 'message' | 'error' | 'open' | 'close' | 'reconnecting', cb)
  close()
  // 内部:指数退避重连,最大间隔 30s
}
```

使用场景:实时日志、实例 testRun 输出、扫描进度、运行历史 live。

### 6.4 类型生成

OpenAPI → TypeScript:推荐 `openapi-typescript` + `openapi-fetch`。

- 后端 FastAPI 在 `/openapi.json` 暴露 schema
- 开发期跑 `pnpm gen:types`(脚本调用 `openapi-typescript /openapi.json -o src/types/api.gen.ts`)
- API 方法手写但参数/返回类型用生成的 types,确保编译期校验

提交策略:`api.gen.ts` 提交到 git,后端契约一变就重跑脚本 + diff 评审。

### 6.5 错误处理统一

- `ApiError` 类:`{ code, message, status, fields?, requestId? }`
- 组件层捕获后:
  - 字段级错误(fields)→ 高亮表单字段
  - 全局错误 → toast(由拦截器自动处理)
  - 业务错误(如"实例已存在")→ 组件内联显示,不 toast

---

## 7. 响应式策略

桌面优先,但要防止"小屏被搞炸"。

### 7.1 断点

```
2xl: 1536px+   两列 KPI / 4 列脚本卡 / 侧栏永久展开 / 主区 max-width 1440px
xl:  1280-1535 6 KPI / 3-4 脚本卡 / 侧栏展开
lg:  1024-1279 4-6 KPI / 2-3 脚本卡 / 侧栏自动折叠
md:  768-1023  3-4 KPI / 2 脚本卡 / 侧栏抽屉化(点击图标弹出)
sm:  <768     建议提示桌面访问体验更佳,但仍可用:KPI 单列 / 脚本卡单列 / 侧栏抽屉
```

### 7.2 自适应规则

- KPI 网格:`repeat(auto-fit, minmax(200px, 1fr))`,自然回流
- 脚本网格:`repeat(auto-fill, minmax(280px, 1fr))`
- 表格:小屏自动横向滚动 + 关键列粘性(脚本名)
- 抽屉:小屏自动改为底部 sheet(从下方滑入,90vh)
- 顶栏搜索框:`md` 以下隐藏,只显示一个 `Search` 图标按钮
- 路由切换:`<768` 时禁用复杂 transition,只 fade

### 7.3 小屏降级提示

`<768` 首次访问时显示一个底部 banner:
"建议在 1024px+ 桌面浏览器获得最佳体验。"右侧"我知道了"。dismiss 后 7 天不再显示。

---

## 8. 美化关键手法(让 UI 不土的具体技术)

这是项目最核心的部分,**编码 Agent 必须严格遵循,不能偷懒**。

### 8.1 卡片三层质感

每张卡片都要做出"轻盈但有重量"的感觉,具体三件事:

1. **微妙渐变背景**:深色模式下,卡片底色不要纯色,用 `linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 50%)` 叠加在 base color 上,模拟"上方反光"
2. **半透明 border**:深色模式 `1px solid rgba(255,255,255,0.06)`,浅色 `1px solid rgba(0,0,0,0.04)`,而非固定色
3. **hover 抬升**:`transition: transform 200ms, box-shadow 200ms`,hover 时 `transform: translateY(-2px); box-shadow: shadow-md`

### 8.2 数字呈现

- **Tabular Numbers**:全局给数字组件加 `font-feature-settings: 'tnum' 1`,统计数字才不会跳
- **Count-up 动画**:数字变化时用 `@vueuse/motion` 或自写 RAF 实现 count-up,duration 800ms,ease-out
- **千分位**:大数自动加 `,`(用 `Intl.NumberFormat`)
- **百分比**:始终一位小数(96.4%)

### 8.3 状态指示器加呼吸光晕

- "运行中"状态点:不只是色块,在外层加一个同色 `box-shadow: 0 0 0 4px rgba(success, 0.2)`,然后做 scale 1→1.2→1 的 2s 循环动画,产生"呼吸"感
- 仅在状态为 active(运行中、连接中)时启用
- `prefers-reduced-motion: reduce` 时禁用

### 8.4 KPI 加 Sparkline

- 用 `unovis`(Vue 适配好,深浅主题友好)或纯 SVG 折线
- 高度 24-32px,宽度自适应卡片
- 颜色:与卡片 tone 同色但 alpha 0.4 + stroke
- 渐变填充:`url(#gradient-tone)`,从 tone-500 透明 0.3 渐变到 0
- 鼠标 hover 显示 tooltip(具体数值)

### 8.5 路由切换 transition

- 默认用 fade-slide:进入 `opacity 0 + translateY(8px)` → `opacity 1 + translateY(0)`,duration 240ms,easing-decelerate
- 离开 `opacity 1` → `opacity 0`,duration 160ms,easing-accelerate
- `<RouterView v-slot="{ Component }">` + `<transition name="fade-slide" mode="out-in">`
- `prefers-reduced-motion` 时禁用 translateY,只 fade

### 8.6 全局 ⌘K 命令面板

详见 3.10。技术栈:

- 自写 + 借鉴 `vue-cmdk` 或 `cmdk-vue`
- fuse.js 做模糊匹配
- 命令注册:`useCmdkStore().register({ id, label, action, group, keywords })`,各页面进入时注册自己的命令(运行脚本、跳实例配置等)
- 键盘陷阱:打开时禁止 body 滚动,Esc 关闭
- 进入动画:scale + fade,duration 200ms

### 8.7 微交互

- **按钮按下**:`active:scale-[0.99]` + brand-600 底色,弹回 100ms ease-out
- **开关**:用 spring easing,滑块出弹性,0.34, 1.56, 0.64, 1
- **表单 focus**:边框 brand-500 + `box-shadow: 0 0 0 3px rgba(brand, 0.16)`,200ms 过渡
- **复选框/单选**:勾出现时画线动画(stroke-dasharray 0→100,200ms)
- **手势**:hover 时光标变化(button → pointer,grab 区域 → grab)
- **声音**:无!(后台工具,严禁 UI 声音)

### 8.8 暗色模式重新调色

不是简单反色!具体规则:

- **所有文字降亮**:深色模式下"白色"文字用 #E6E8EB 而非 #FFFFFF,长时间观看不刺眼
- **所有背景增蓝**:深色背景偏冷蓝(#0B0D10 而非 #0A0A0A 纯黑),营造"夜晚"氛围
- **饱和度降低**:深色模式下品牌色 brand-500 视觉上更亮,需要降低 5-10% 饱和度,或用 brand-400 替代 brand-500 作主色
- **阴影改半透明黑 + inner highlight**:见 1.7
- **图片/插画**:深色模式自动 `filter: brightness(0.9) contrast(0.95)`(或为深色单独做素材)

### 8.9 图标系统

- **库**:`unplugin-icons` + `@iconify-json/lucide`(主)+ `@iconify-json/simple-icons`(品牌图标如 Telegram、Bark)
- **使用方式**:`<i-lucide-package />` 直接导入,tree-shake 友好
- **大小**:统一 16/18/20/24/32px 五档
- **颜色**:继承 `currentColor`,跟随文字色
- **绝不混用**:同一项目内只用 Lucide(线条风),禁止 Material 实心、FontAwesome 等混用

### 8.10 数据可视化

- **首选**:`unovis`(Vue 适配好,主题适配,默认配色高级)
- **备选**:`echarts`(功能强但默认样式土,需大量定制)
- **mini sparkline**:可以纯 SVG `<polyline>` 自写
- **配色**:从设计 token 取色,严格使用我们定义的 brand/accent/语义色,不用 echarts 默认 palette
- **暗色模式**:监听主题变化重渲染图表,字体色、网格线色、tooltip 背景都要换

### 8.11 空状态插画

- **首选**:自绘 SVG(简洁、可控、深色友好)
- **备选**:`unDraw`(免费 SVG 插画,可改色)
- **避免**:Lottie 动画(体积大、可能卡顿、不必要)
- **风格统一**:线条插画,主色用 brand,辅助色 neutral-300/400

### 8.12 文字与排版细节

- **首字大写**:中文不需要,英文界面文案首字大写(如 "Settings" 不用 "settings")
- **中英混排**:中英之间留半角空格(如 "已发送 23 条")
- **数字与单位**:数字后单位用空格(`1.2 s`、`128 MB`)
- **省略号**:用 `…` 而非 `...`
- **引号**:中文用「」,英文用 `""`
- **破折号**:统一用 `——`(两个全角)
- **CSS 上**:`text-rendering: optimizeLegibility`、`-webkit-font-smoothing: antialiased`、`-moz-osx-font-smoothing: grayscale` 全局开

### 8.13 滚动条美化

- 浅色:轨道透明,thumb `rgba(0,0,0,0.18)`,hover `rgba(0,0,0,0.28)`,宽 8px,圆角 4px
- 深色:thumb `rgba(255,255,255,0.12)`,hover `rgba(255,255,255,0.22)`
- WebKit + Firefox(`scrollbar-width: thin; scrollbar-color: ...`)都要写

### 8.14 Loading Skeleton 闪光动效

```
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, neutral-200 0%, neutral-100 50%, neutral-200 100%);
  background-size: 200% 100%;
  animation: shimmer 1.6s linear infinite;
}
```

`prefers-reduced-motion: reduce` 时禁用 animation,改用静态 `neutral-150`。

### 8.15 自定义滚动条 + scroll snap

仪表盘、脚本卡片网格在窄屏时切换为水平滚动 + scroll-snap-type,体验类似手机 banner。

---

## 9. 推荐目录结构

```
frontend/
├── public/
│   ├── favicon.svg
│   └── og-image.png
├── src/
│   ├── api/                # API 封装
│   │   ├── http.ts         # axios 实例 + 拦截器
│   │   ├── sse.ts          # SSE 客户端
│   │   ├── auth.ts
│   │   ├── scripts.ts
│   │   ├── instances.ts
│   │   ├── runs.ts
│   │   ├── notifications.ts
│   │   └── settings.ts
│   ├── assets/             # 静态资源(图片、字体、SVG 插画)
│   │   ├── fonts/
│   │   ├── illustrations/
│   │   └── logo.svg
│   ├── components/         # 公共组件(无业务依赖)
│   │   ├── base/           # 基础组件 Badge/Button/Input 重写
│   │   ├── layout/         # Topbar, Sidebar, AppLayout, PublicLayout
│   │   ├── data/           # KpiCard, MiniSparkline, RelativeTime
│   │   ├── feedback/       # EmptyState, ErrorBoundary, ConfirmDialog, Toast
│   │   ├── form/           # SecretInput, CronInput, FieldError, CollapsibleSection
│   │   ├── log/            # LogViewer
│   │   └── cmdk/           # CommandPalette
│   ├── composables/        # 可复用逻辑 hooks
│   │   ├── useTheme.ts
│   │   ├── useSse.ts
│   │   ├── useApi.ts       # 简化 API 调用 + loading/error 状态
│   │   ├── useShortcuts.ts
│   │   ├── useDebounce.ts
│   │   └── useVirtualList.ts
│   ├── layouts/            # 页面布局
│   │   ├── AppLayout.vue
│   │   └── PublicLayout.vue
│   ├── pages/              # 路由级页面(每页一个文件夹,内含 .vue + 子组件)
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── scripts/
│   │   ├── runs/
│   │   ├── notifications/
│   │   ├── settings/
│   │   └── error/
│   ├── router/
│   │   ├── index.ts        # 路由表 + guard
│   │   └── routes.ts       # 路由数组
│   ├── stores/             # Pinia stores
│   │   ├── auth.ts
│   │   ├── scripts.ts
│   │   ├── instances.ts
│   │   ├── runs.ts
│   │   ├── notifications.ts
│   │   ├── settings.ts
│   │   └── ui.ts
│   ├── styles/             # 全局样式
│   │   ├── tokens/         # CSS variables(颜色/间距/字体/阴影)
│   │   │   ├── colors.scss
│   │   │   ├── typography.scss
│   │   │   ├── spacing.scss
│   │   │   ├── shadows.scss
│   │   │   └── motion.scss
│   │   ├── themes/         # light.scss / dark.scss(覆盖 token)
│   │   ├── base.scss       # reset + 全局基础(html/body/scrollbar)
│   │   ├── element-plus-overrides.scss   # Element Plus 主题覆盖
│   │   └── main.scss       # 入口聚合
│   ├── types/              # TS 类型
│   │   ├── api.gen.ts      # OpenAPI 自动生成
│   │   ├── domain.ts       # 业务领域模型
│   │   └── ui.ts           # UI 相关类型(Toast、Theme 等)
│   ├── utils/              # 纯工具函数
│   │   ├── date.ts         # dayjs 包装
│   │   ├── cron.ts         # cron 解析 + 翻译
│   │   ├── format.ts       # 数字/字节/百分比格式化
│   │   ├── ansi.ts         # ANSI 解析
│   │   ├── nanoid.ts
│   │   └── storage.ts      # localStorage 包装
│   ├── App.vue             # 根组件(挂 toast、cmdk、theme provider)
│   ├── main.ts             # 入口
│   └── env.d.ts
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── .env                    # VITE_API_BASE 等
├── .env.development
├── .env.production
├── .eslintrc.cjs
├── .prettierrc
└── README.md
```

每个目录一句话职责:

- `api/` —— 所有 HTTP/SSE 调用,无 UI 依赖,可被任意 store/component 调用
- `assets/` —— 静态资源,字体本地化、SVG 插画、品牌物料
- `components/` —— 跨页面复用的 UI 组件,**不直接调 API**(必须通过 props 接收数据或 emit 事件)
- `composables/` —— Vue 3 hooks,封装可复用逻辑(主题、SSE、防抖、API 状态机)
- `layouts/` —— 大型骨架布局,包含 router-view 槽位
- `pages/` —— 路由对应的页面组件,**唯一允许直接调 store/api 的层级**
- `router/` —— 路由表 + 鉴权 guard + 标题设置
- `stores/` —— Pinia 全局状态
- `styles/` —— 全局样式 + 设计 token + Element Plus 覆盖
- `types/` —— TS 类型集中管理
- `utils/` —— 纯函数工具

---

## 10. 关键依赖建议(package.json 风格)

```jsonc
{
  "dependencies": {
    // 核心
    "vue": "^3.5.0",
    "vue-router": "^4.4.0",
    "pinia": "^2.2.0",
    "pinia-plugin-persistedstate": "^4.0.0",

    // UI 库 + 重度美化
    "element-plus": "^2.8.0",
    "@element-plus/icons-vue": "^2.3.0",  // 备用,主用 lucide

    // 图标
    "@iconify-json/lucide": "^1.2.0",
    "@iconify-json/simple-icons": "^1.2.0",

    // 工具
    "axios": "^1.7.0",
    "@microsoft/fetch-event-source": "^2.0.1",  // SSE 增强
    "dayjs": "^1.11.13",
    "lodash-es": "^4.17.21",
    "nanoid": "^5.0.7",
    "fuse.js": "^7.0.0",                         // ⌘K 模糊搜索
    "marked": "^14.1.0",                         // README 渲染
    "highlight.js": "^11.10.0",                  // 代码高亮
    "ansi_up": "^6.0.2",                         // 日志 ANSI

    // 表单/cron
    "cronstrue": "^2.50.0",
    "cron-parser": "^4.9.0",

    // 动画 / 数据可视化
    "@vueuse/core": "^11.0.0",
    "@vueuse/motion": "^2.2.5",
    "@unovis/vue": "^1.4.0",                     // 主用图表
    "@vue-flow/core": "^1.41.0",                 // 备用(规则可视化等)

    // 列表虚拟化
    "vue-virtual-scroller": "^2.0.0-beta.8"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.1.0",
    "vite": "^5.4.0",
    "typescript": "^5.6.0",
    "vue-tsc": "^2.1.0",

    // 自动导入 + 图标 + 组件
    "unplugin-auto-import": "^0.18.0",
    "unplugin-vue-components": "^0.27.0",
    "unplugin-icons": "^0.19.0",
    "@iconify/vue": "^4.1.2",

    // SCSS
    "sass": "^1.78.0",

    // 代码生成
    "openapi-typescript": "^7.4.0",

    // Lint / Format
    "eslint": "^9.0.0",
    "@vue/eslint-config-typescript": "^14.0.0",
    "prettier": "^3.3.0"
  }
}
```

`vite.config.ts` 关键插件配置(描述,不写代码):

- `@vitejs/plugin-vue`
- `unplugin-vue-components/vite`(自动注册 Element Plus 与本地 components)
- `unplugin-auto-import/vite`(自动导入 Vue/Pinia/router API)
- `unplugin-icons/vite`(图标自动导入)
- alias `@` → `src/`
- 开发期 proxy `/api` → 后端地址
- 生产期 chunk 拆分:`element-plus`、`unovis`、`marked+highlight`、`vendor` 各自独立

---

## 附录 A:命名约定

- 文件:Vue 组件 PascalCase(`KpiCard.vue`),工具/store/api kebab-case 或 camelCase 文件 + camelCase 导出(`use-theme.ts` 或 `useTheme.ts` 二选一,推荐 camelCase)
- CSS 类:BEM 不强制,内部用 `<style scoped>`,公共样式用 token 变量
- 事件:`kebab-case`(`@row-click`,`@status-change`)
- props:`camelCase`(模板里 `kebab-case` 自动转换)
- store:`useXxxStore` 命名,文件 `xxx.ts`
- 路由 name:`kebab-case`(`script-detail`)

## 附录 B:可访问性 a11y 底线

- 所有 icon button 必须有 `aria-label`
- Modal/抽屉打开后 focus trap,Esc 关闭
- 键盘可达:tab 顺序合理,所有交互元素 focus 可见(focus ring)
- 颜色对比度 WCAG AA(正文 4.5:1,大字 3:1)
- 动效尊重 `prefers-reduced-motion`

## 附录 C:性能底线

- 首屏 JS gzipped < 250KB(含 Element Plus 按需 + Vue + 路由)
- 单页路由懒加载
- 长列表(执行历史、日志)必须虚拟滚动
- 图片懒加载(`loading="lazy"`)
- SSE 连接 idle > 5min 自动断开,操作时再重连
- Lighthouse Performance > 85,Accessibility > 95

## 附录 D:验收清单(给编码 agent 自检用)

完成后 self-check 这些点:

- [ ] 浅色与深色模式都能看,两套都精致(不是简单反色)
- [ ] 主题切换时所有组件实时更新无闪烁
- [ ] 所有空状态都有专门的设计,不是默认的"暂无数据"
- [ ] 所有按钮 hover/active/disabled/loading 四态都设计过
- [ ] 所有表单字段有 label / placeholder / error / disabled / focus 五态
- [ ] Cron 输入框有人话翻译和下次执行预览
- [ ] Secret 输入框可以显隐和复制,且复制有反馈
- [ ] 实时日志的 SSE 重连能工作,断网后自动恢复
- [ ] ⌘K 命令面板能打开,能搜索能跳转
- [ ] 路由切换有 fade-slide 过渡
- [ ] 数字变化有 count-up 动效
- [ ] 至少有一个 KPI 卡片展示了 sparkline
- [ ] Element Plus 的灰扁平默认外观看不见任何痕迹(检查表格、对话框、选择器、消息提示)
- [ ] 中英混排有空格,数字 tabular-nums 不跳字
- [ ] 1280px / 1024px / 768px 三个断点下都能使用

---

*本设计文档为编码 Agent 的实现契约。所有视觉、交互、组件结构必须严格遵循。如遇歧义,以"克制、现代、精致"三词作为最终裁判。*

---

### Critical Files for Implementation

由于项目目录目前为空(全新项目),实现时应优先创建以下 5 个文件作为整个前端的奠基。所有路径均为绝对路径。

- `E:\签到脚本多合一\frontend\src\styles\tokens\colors.scss` — 设计 token 色彩定义(浅深两套 CSS 变量),所有组件颜色必须从这里取
- `E:\签到脚本多合一\frontend\src\styles\element-plus-overrides.scss` — Element Plus 主题深度覆盖,确保去除"灰扁平"默认外观,这是"美化"成败关键
- `E:\签到脚本多合一\frontend\src\layouts\AppLayout.vue` — 主体三段式布局(顶栏 + 侧栏 + 内容区),挂载 toast/⌘K/主题切换的容器
- `E:\签到脚本多合一\frontend\src\stores\ui.ts` — UI 状态管理(主题、侧栏、命令面板、toast),全局视觉状态的单一来源
- `E:\签到脚本多合一\frontend\src\components\data\KpiCard.vue` — KPI 卡片(含图标、数字 count-up、sparkline、trend),作为"精致后台"视觉范式的标杆组件,其余卡片需对齐其品质