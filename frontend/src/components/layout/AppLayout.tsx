/**
 * <AppLayout> — 已登录主区布局(2026-05-16 重构版)
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 2.3.2(AppLayout)、§ 8。
 *
 * 重构原因(放弃 shadcn Sidebar):
 *   - shadcn Sidebar 内部 SidebarProvider + Sidebar(fixed div + gap div + peer)+ SidebarInset
 *     三层嵌套 + 大量 md: hardcoded breakpoint + isMobile 切 Sheet overlay,反复修无法稳定让位
 *   - 真正需要的:**两列 CSS Grid,纯 layout flow,无 fixed/absolute,无 isMobile 分支**
 *
 * 结构(2 列 CSS Grid,grid-template-columns 由 collapsed 动态控制):
 *   ┌──────────┬───────────────────────────────┐
 *   │ Sidebar  │ Topbar(sticky 56px)         │ ← 顶栏在 main 列内
 *   │ (64px /  ├───────────────────────────────┤
 *   │  240px)  │ <Outlet /> 主区(自适应)      │
 *   └──────────┴───────────────────────────────┘
 *
 * 响应式:
 *   - 任何 viewport(320px–4K)都自动 push 不 overlay,grid 1fr 自动算 main 宽度
 *   - 没有固定 px 阈值(无 useIsMobile / md: 之类)
 *   - 折叠状态由 useUIStore.sidebarCollapsed 控制,persist 到 localStorage
 *   - 折叠态(64px)只显图标,hover 弹 Tooltip 显示文字
 */
import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate, NavLink } from 'react-router';
import {
  LayoutDashboard,
  ScrollText,
  Activity,
  Bell,
  Settings,
  LogOut,
  Menu,
  User as UserIcon,
  Sun,
  Moon,
  Monitor,
  Search,
  ChevronsUpDown,
  Server,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useUIStore } from '@/stores/ui.store';
import { useAuthStore } from '@/stores/auth.store';
import { useCurrentUser, useLogout, meToAuthUser } from '@/api/hooks/auth';
import { useAppearance, DEFAULT_APPEARANCE } from '@/api/hooks/appearance';
import { cn } from '@/lib/utils';
import { CommandPalette } from '@/components/common/CommandPalette';

/* ============ 主题切换 ============ */

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-9" aria-label="切换主题">
          <Sun
            size={16}
            strokeWidth={1.75}
            className="rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0"
          />
          <Moon
            size={16}
            strokeWidth={1.75}
            className="absolute rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-32">
        <DropdownMenuItem onClick={() => setTheme('light')}>
          <Sun size={14} strokeWidth={1.75} className="mr-2" />
          <span>浅色</span>
          {theme === 'light' && (
            <span className="ml-auto text-xs text-muted-foreground">·</span>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme('dark')}>
          <Moon size={14} strokeWidth={1.75} className="mr-2" />
          <span>深色</span>
          {theme === 'dark' && (
            <span className="ml-auto text-xs text-muted-foreground">·</span>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme('system')}>
          <Monitor size={14} strokeWidth={1.75} className="mr-2" />
          <span>跟随系统</span>
          {theme === 'system' && (
            <span className="ml-auto text-xs text-muted-foreground">·</span>
          )}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* ============ 用户菜单 ============ */

function UserMenu() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const storeUser = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { mutateAsync: logout, isPending } = useLogout();

  const u = user ? meToAuthUser(user) : storeUser;
  const displayName = u?.displayName || u?.username || '用户';
  const initials = (u?.displayName ?? u?.username ?? 'U').slice(0, 1).toUpperCase();

  async function handleLogout() {
    try {
      await logout();
      clearUser();
      toast.success('已退出登录');
      navigate('/login', { replace: true });
    } catch {
      // mutation onError 已 toast
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 px-2" aria-label="用户菜单">
          <Avatar className="size-7">
            <AvatarFallback className="bg-primary/15 text-xs font-semibold text-primary">
              {initials}
            </AvatarFallback>
          </Avatar>
          <span className="hidden text-sm font-medium sm:inline">{displayName}</span>
          <ChevronsUpDown size={14} strokeWidth={1.75} className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-0.5">
            <p className="text-sm font-medium">{displayName}</p>
            {u?.username && u.displayName ? (
              <p className="text-xs text-muted-foreground">@{u.username}</p>
            ) : null}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/settings')}>
          <UserIcon size={14} strokeWidth={1.75} className="mr-2" />
          <span>账户设置</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={handleLogout}
          disabled={isPending}
          className="text-danger focus:text-danger"
        >
          <LogOut size={14} strokeWidth={1.75} className="mr-2" />
          <span>{isPending ? '退出中…' : '退出登录'}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* ============ 导航定义 ============ */

interface NavItem {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { label: '仪表盘', to: '/dashboard', icon: LayoutDashboard },
  { label: '脚本', to: '/scripts', icon: ScrollText },
  { label: '执行', to: '/runs', icon: Activity },
  { label: '节点', to: '/nodes', icon: Server },
  { label: '通知', to: '/notifications', icon: Bell },
  { label: '设置', to: '/settings', icon: Settings },
];

/* ============ 侧栏(纯 aside,无 portal/fixed/sheet)============ */

function Sidebar({
  collapsed,
  onToggle,
  logoImageUrl,
  logoText,
  siteTitle,
  siteSubtitle,
}: {
  collapsed: boolean;
  onToggle: () => void;
  logoImageUrl?: string;
  logoText?: string;
  siteTitle?: string;
  siteSubtitle?: string;
}) {
  const location = useLocation();
  return (
    <aside
      data-collapsed={collapsed || undefined}
      className={cn(
        'group/sidebar flex h-full flex-col overflow-hidden',
        'border-r border-border bg-card text-card-foreground',
      )}
    >
      {/* Header(品牌 / 折叠 toggle) — 整个区域可点击切换折叠态,UI 更自然 */}
      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
        title={collapsed ? '点击展开侧栏' : '点击折叠侧栏'}
        className={cn(
          'flex h-14 w-full shrink-0 items-center gap-2 border-b border-border px-3 text-left',
          'transition-colors hover:bg-accent/40',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
        )}
      >
        <div className="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-primary text-primary-foreground shadow-sm">
          {logoImageUrl ? (
            <img
              src={logoImageUrl}
              alt={siteTitle ?? 'Logo'}
              className="size-full object-cover"
              draggable={false}
            />
          ) : (
            <span className="text-sm font-bold tracking-tight">
              {logoText || '签'}
            </span>
          )}
        </div>
        {!collapsed && (
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold tracking-tight">
              {siteTitle || '签到管家'}
            </span>
            {siteSubtitle ? (
              <span className="truncate text-[10px] font-medium text-muted-foreground">
                {siteSubtitle}
              </span>
            ) : null}
          </div>
        )}
      </button>

      {/* Nav 列表 */}
      <nav className="flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              location.pathname === item.to ||
              location.pathname.startsWith(item.to + '/');
            const linkEl = (
              <NavLink
                to={item.to}
                className={cn(
                  'group/nav flex h-9 items-center gap-2 rounded-md px-2 text-sm transition-colors',
                  collapsed && 'justify-center',
                  isActive
                    ? 'bg-accent text-accent-foreground font-medium'
                    : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
                )}
              >
                <Icon size={18} strokeWidth={1.75} className="shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </NavLink>
            );
            return (
              <li key={item.to}>
                {collapsed ? (
                  <Tooltip>
                    <TooltipTrigger asChild>{linkEl}</TooltipTrigger>
                    <TooltipContent side="right">{item.label}</TooltipContent>
                  </Tooltip>
                ) : (
                  linkEl
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="px-3 py-2 text-[10px] leading-tight text-muted-foreground border-t border-border">
          <p>本地调度 · 服务端会话</p>
        </div>
      )}
    </aside>
  );
}

/* ============ 主布局 ============ */

const SIDEBAR_WIDTH = 240;
const SIDEBAR_WIDTH_COLLAPSED = 64;

export function AppLayout() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const toggleCommandPalette = useUIStore((s) => s.toggleCommandPalette);
  const location = useLocation();
  const navigate = useNavigate();

  // 应用外观品牌设置(站点标题 / logo / 背景图)— PR #8
  const { data: appearance } = useAppearance();
  const app = appearance ?? DEFAULT_APPEARANCE;

  // mobile sidebar 抽屉状态(< md 时启用,desktop 始终用 inline grid sidebar)— PR #7
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // 路由切换时自动关 mobile sidebar(用户点导航后不需要手动关)— PR #7
  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [location.pathname]);

  // document.title 同步(浏览器 tab 显示)— PR #8
  useEffect(() => {
    if (app.site_title) {
      document.title = app.site_title;
    }
  }, [app.site_title]);

  // favicon 自动从 logo 生成 — PR #8
  // 🟡 MED · code-review #7+#8+#9 修复:
  // - #7 加 palette 改色监听(自定义事件)→ 改主题色后 favicon 重绘
  // - #8 cleanup: cancel flag 防 img.onload 在 effect rerun 后覆盖新 favicon
  // - #9 querySelectorAll 全替换 link[rel*="icon"](含 apple-touch-icon / shortcut),
  //      iOS 主屏 / 旧浏览器收藏夹也同步
  const [paletteVersion, setPaletteVersion] = useState(0);
  useEffect(() => {
    function onPaletteChanged() {
      setPaletteVersion((v) => v + 1);
    }
    window.addEventListener('palette:changed', onPaletteChanged);
    return () => window.removeEventListener('palette:changed', onPaletteChanged);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const applyToFavicon = () => {
      if (cancelled) return;
      const dataUrl = canvas.toDataURL('image/png');
      // 全替换所有 link[rel] 含 icon 的(icon / shortcut icon / apple-touch-icon)
      const links = document.querySelectorAll<HTMLLinkElement>(
        'link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]',
      );
      if (links.length === 0) {
        const link = document.createElement('link');
        link.rel = 'icon';
        link.type = 'image/png';
        link.href = dataUrl;
        document.head.appendChild(link);
      } else {
        links.forEach((link) => {
          link.type = 'image/png';
          link.href = dataUrl;
        });
      }
    };

    if (app.logo_image_data_url) {
      const img = new Image();
      img.onload = () => {
        if (cancelled) return;
        ctx.clearRect(0, 0, 64, 64);
        // 圆角剪裁 + cover 绘图
        ctx.save();
        const r = 12;
        ctx.beginPath();
        ctx.moveTo(r, 0);
        ctx.lineTo(64 - r, 0);
        ctx.quadraticCurveTo(64, 0, 64, r);
        ctx.lineTo(64, 64 - r);
        ctx.quadraticCurveTo(64, 64, 64 - r, 64);
        ctx.lineTo(r, 64);
        ctx.quadraticCurveTo(0, 64, 0, 64 - r);
        ctx.lineTo(0, r);
        ctx.quadraticCurveTo(0, 0, r, 0);
        ctx.closePath();
        ctx.clip();
        ctx.drawImage(img, 0, 0, 64, 64);
        ctx.restore();
        applyToFavicon();
      };
      img.onerror = () => {
        // 加载失败 fallback 文字
        drawTextFavicon();
      };
      img.src = app.logo_image_data_url;
    } else {
      drawTextFavicon();
    }

    function drawTextFavicon() {
      if (!ctx) return;
      // 主题色(从 localStorage 取自定义色,fallback indigo)
      let primary = '#5865F2';
      try {
        primary = localStorage.getItem('signin-panel-palette-hex') || primary;
      } catch {
        // ignore
      }
      ctx.clearRect(0, 0, 64, 64);
      // 圆角背景
      ctx.fillStyle = primary;
      const r = 12;
      ctx.beginPath();
      ctx.moveTo(r, 0);
      ctx.lineTo(64 - r, 0);
      ctx.quadraticCurveTo(64, 0, 64, r);
      ctx.lineTo(64, 64 - r);
      ctx.quadraticCurveTo(64, 64, 64 - r, 64);
      ctx.lineTo(r, 64);
      ctx.quadraticCurveTo(0, 64, 0, 64 - r);
      ctx.lineTo(0, r);
      ctx.quadraticCurveTo(0, 0, r, 0);
      ctx.closePath();
      ctx.fill();
      // 文字(用 sidebar_logo_text,1-2 字)
      const text = (app.sidebar_logo_text || '签').slice(0, 2);
      ctx.fillStyle = '#fff';
      ctx.font = text.length === 1 ? 'bold 44px system-ui, sans-serif' : 'bold 28px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 32, 36);
      applyToFavicon();
    }

    // cleanup:effect rerun 或 unmount 时 set cancel flag,
    // 已 in-flight 的 img.onload 检查 cancelled 跳过 applyToFavicon
    return () => {
      cancelled = true;
    };
  }, [app.logo_image_data_url, app.sidebar_logo_text, paletteVersion]);

  // 401 → /login
  useEffect(() => {
    function handler() {
      const from = location.pathname + location.search;
      navigate(`/login?from=${encodeURIComponent(from)}`, { replace: true });
    }
    window.addEventListener('app:unauthorized', handler);
    return () => window.removeEventListener('app:unauthorized', handler);
  }, [navigate, location.pathname, location.search]);

  const sidebarWidth = sidebarCollapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH;

  // 背景图 inline style — 应用到 main 内部 min-h-full 包装(随 scroll content 等高,
  // 不是 main viewport),这样滚动到底部背景仍覆盖,且 overlay 跟着一起延伸
  const hasBackground = !!app.background_image_data_url;
  const backgroundWrapperStyle: React.CSSProperties = hasBackground
    ? {
        backgroundImage: `url("${app.background_image_data_url}")`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        // background-attachment 用默认 'scroll' — 跟 wrapper(min-h-full)一起滚动,
        // overlay 也跟 wrapper 一起延伸,两者始终对齐覆盖完整 scroll content
        // (用 'fixed' 会跟 overlay 移动错位,且视觉上覆盖 sidebar)
        backgroundBlendMode: app.background_blend_mode || 'normal',
      }
    : {};

  // 浅深色 overlay 颜色区分:浅色主题用白罩 / 深色主题用黑罩
  // 🟢 LOW · code-review #15:resolvedTheme 首次 mount 是 undefined(next-themes
  // 避免 hydration mismatch)。**反转默认到 light/白罩** — 浅色用户首屏不闪烁;
  // 深色用户首帧白罩 1 帧再变黑罩(深色背景图通常已经偏暗,白罩 1 帧不太刺眼)
  const { resolvedTheme } = useTheme();
  const overlayRGB =
    resolvedTheme === 'dark' ? '0, 0, 0' : '255, 255, 255';

  // 🟡 MED · code-review #12:NaN clamp 失效兜底
  // Math.max(0, Math.min(1, NaN)) = NaN → rgba(...,NaN) invalid CSS → 浏览器忽略
  // 用户改 devtools / 后端 validator 绕过 / fetchAppearance 兜底失效都可能传 NaN
  const safeOpacity = Number.isFinite(app.background_opacity)
    ? Math.max(0, Math.min(1, app.background_opacity))
    : 0.3;
  const safeBlur = Number.isFinite(app.background_blur)
    ? Math.max(0, Math.min(40, app.background_blur))
    : 0;

  // 背景图模糊覆盖层 + opacity 罩 — absolute inset: 0 相对 min-h-full 包装,
  // 跟 scroll content 等高,滚动到底部仍被覆盖
  const backgroundOverlayStyle: React.CSSProperties = hasBackground
    ? {
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        // opacity=1 → 全透明(完全看清背景图),opacity=0 → 全色遮罩(完全隐藏背景图)
        backgroundColor: `rgba(${overlayRGB}, ${1 - safeOpacity})`,
        backdropFilter: safeBlur > 0 ? `blur(${safeBlur}px)` : undefined,
        WebkitBackdropFilter: safeBlur > 0 ? `blur(${safeBlur}px)` : undefined,
      }
    : {};

  // 🟢 LOW · code-review #13:resize 到 md+ 时关闭 mobile Sheet
  // Sheet 用 md:hidden 控制内容显隐,但组件本身始终挂载。mobileSidebarOpen=true
  // 时 resize 到 desktop,Radix 在 display:none 元素 trap focus → 键盘 Tab 锁死,
  // a11y screen reader 念诵异常。
  useEffect(() => {
    const mediaQuery = window.matchMedia('(min-width: 768px)');
    function onChange(e: MediaQueryListEvent) {
      if (e.matches) setMobileSidebarOpen(false);
    }
    mediaQuery.addEventListener('change', onChange);
    return () => mediaQuery.removeEventListener('change', onChange);
  }, []);

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className={cn(
          'flex h-screen w-full overflow-hidden bg-background',
          // < md: 纯 flex(sidebar 不参与 grid,改 mobile Sheet);
          // >= md: CSS Grid 2 列(sidebar 列宽动态,main 列 1fr)
          'md:grid',
        )}
        style={{
          gridTemplateColumns: `${sidebarWidth}px 1fr`,
          transition: 'grid-template-columns 200ms ease',
        }}
      >
        {/* Desktop sidebar — md+ 直接渲染在 grid 第 1 列(PR #7 mobile 抽屉 + PR #8 logo/title props 融合) */}
        <div className="hidden md:block">
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
            logoImageUrl={app.logo_image_data_url}
            logoText={app.sidebar_logo_text}
            siteTitle={app.site_title}
            siteSubtitle={app.site_subtitle}
          />
        </div>

        {/* Mobile sidebar — < md 用 Sheet 抽屉,从左边滑入,backdrop 点击关 */}
        <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
          <SheetContent
            side="left"
            className="w-[260px] border-r-0 p-0 md:hidden"
          >
            {/* mobile 上 sidebar 始终展开态(不折叠),点 logo 关闭抽屉;也接 logo/title props */}
            <Sidebar
              collapsed={false}
              onToggle={() => setMobileSidebarOpen(false)}
              logoImageUrl={app.logo_image_data_url}
              logoText={app.sidebar_logo_text}
              siteTitle={app.site_title}
              siteSubtitle={app.site_subtitle}
            />
          </SheetContent>
        </Sheet>

        {/* 主区(顶栏 + Outlet),纵向 flex 让顶栏 sticky 在自己内部 */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Topbar — mobile 加汉堡按钮在左,desktop 隐藏(直接显搜索) */}
          <header
            className={cn(
              'sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border',
              'bg-background/70 backdrop-blur-md',
              'px-3 sm:px-4 lg:px-6',
            )}
          >
            {/* 汉堡按钮 — 仅 mobile 可见 */}
            <Button
              variant="ghost"
              size="icon"
              className="size-9 shrink-0 md:hidden"
              onClick={() => setMobileSidebarOpen(true)}
              aria-label="打开侧栏"
            >
              <Menu size={18} strokeWidth={1.75} />
            </Button>

            {/* 全局搜索 / ⌘K */}
            <button
              type="button"
              onClick={() => toggleCommandPalette()}
              className={cn(
                'group flex h-9 max-w-md flex-1 items-center gap-2 rounded-md border border-border',
                'bg-muted/40 px-3 text-sm text-muted-foreground transition-colors',
                'hover:bg-muted/70 hover:text-foreground',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              )}
              aria-label="打开命令面板"
              title="⌘K 命令面板"
            >
              <Search size={14} strokeWidth={1.75} className="shrink-0" />
              <span className="flex-1 truncate text-left">
                <span className="hidden sm:inline">搜索 / 跳转 / 命令…</span>
                <span className="sm:hidden">搜索</span>
              </span>
              <kbd className="hidden rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground sm:inline">
                ⌘K
              </kbd>
            </button>

            <div className="ml-auto flex items-center gap-1.5">
              <ThemeSwitcher />
              <UserMenu />
            </div>
          </header>

          {/* 主区滚动容器 — main 自己只负责滚动,
              背景图 + overlay 套在内部 min-h-full 包装(随 scroll content 等高,
              滚动到底部都能覆盖,不会露出 raw 背景图)— PR #8;
              内层 outlet 容器用 mobile-first padding(px-3 py-4 sm:px-6 sm:py-6 lg:px-8)— PR #7 融合 */}
          <main className="flex-1 overflow-auto">
            <div
              className="relative min-h-full"
              style={backgroundWrapperStyle}
            >
              {hasBackground ? (
                <div style={backgroundOverlayStyle} aria-hidden="true" />
              ) : null}
              <div className="relative z-[1] mx-auto w-full max-w-[1440px] px-3 py-4 sm:px-6 sm:py-6 lg:px-8">
                <Outlet />
              </div>
            </div>
          </main>
        </div>

        {/* ⌘K 全局命令面板 */}
        <CommandPalette />
      </div>
    </TooltipProvider>
  );
}

export default AppLayout;
