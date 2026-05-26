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
import { useEffect } from 'react';
import { Outlet, useLocation, useNavigate, NavLink } from 'react-router';
import {
  LayoutDashboard,
  ScrollText,
  Activity,
  Bell,
  Settings,
  LogOut,
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

  // 应用外观品牌设置(站点标题 / logo / 背景图)
  const { data: appearance } = useAppearance();
  const app = appearance ?? DEFAULT_APPEARANCE;

  // document.title 同步(浏览器 tab 显示)
  useEffect(() => {
    if (app.site_title) {
      document.title = app.site_title;
    }
  }, [app.site_title]);

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

  // 背景图 inline style(应用到 main 滚动容器)
  const hasBackground = !!app.background_image_data_url;
  const mainStyle: React.CSSProperties = hasBackground
    ? {
        backgroundImage: `url("${app.background_image_data_url}")`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        backgroundBlendMode: app.background_blend_mode || 'normal',
      }
    : {};

  // 背景图模糊覆盖层 + opacity 暗罩(用 ::before pseudo 不行,用 overlay div)
  const backgroundOverlayStyle: React.CSSProperties = hasBackground
    ? {
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        // opacity=1 → 全透明(完全看清背景图),opacity=0 → 全黑遮罩(完全隐藏背景图)
        backgroundColor: `rgba(0, 0, 0, ${1 - Math.max(0, Math.min(1, app.background_opacity))})`,
        backdropFilter: app.background_blur > 0 ? `blur(${app.background_blur}px)` : undefined,
        WebkitBackdropFilter: app.background_blur > 0 ? `blur(${app.background_blur}px)` : undefined,
      }
    : {};

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="grid h-screen w-full overflow-hidden bg-background"
        // CSS Grid 2 列;sidebar 列宽动态,main 列 1fr 自动占剩余 — 任何 viewport 都自动响应
        style={{
          gridTemplateColumns: `${sidebarWidth}px 1fr`,
          transition: 'grid-template-columns 200ms ease',
        }}
      >
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          logoImageUrl={app.logo_image_data_url}
          logoText={app.sidebar_logo_text}
          siteTitle={app.site_title}
          siteSubtitle={app.site_subtitle}
        />

        {/* 主区(顶栏 + Outlet),纵向 flex 让顶栏 sticky 在自己内部 */}
        <div className="flex min-w-0 flex-col overflow-hidden">
          {/* Topbar — 折叠 toggle 已合并到 sidebar 品牌区(点 logo/标题即可),这里去掉重复按钮 */}
          <header
            className={cn(
              'sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border',
              'bg-background/70 backdrop-blur-md',
              'px-4 sm:px-6',
            )}
          >
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
              <Search size={14} strokeWidth={1.75} />
              <span className="flex-1 text-left truncate">搜索 / 跳转 / 命令…</span>
              <kbd className="hidden rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground sm:inline">
                ⌘K
              </kbd>
            </button>

            <div className="ml-auto flex items-center gap-1.5">
              <ThemeSwitcher />
              <UserMenu />
            </div>
          </header>

          {/* 主区滚动容器 — 含可选背景图 + overlay(opacity 暗罩 + 模糊) */}
          <main className="relative flex-1 overflow-auto" style={mainStyle}>
            {hasBackground ? (
              <div style={backgroundOverlayStyle} aria-hidden="true" />
            ) : null}
            <div className="relative z-[1] mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
              <Outlet />
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
