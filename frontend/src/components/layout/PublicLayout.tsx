/**
 * <PublicLayout> — 登录 / setup 专用全屏布局
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 2.3.1(PublicLayout)、§ 3.1(登录页背景)、§ 8(mesh blob 美化)。
 *
 * 视觉:
 *   - 全屏(min-h-screen) + 居中(grid place-items-center)
 *   - 背景层叠 3 个柔焦 mesh blob:indigo(主)/ teal(强调)/ amber(暖)
 *   - 每个 blob:480-520px square,blur-3xl,opacity 30-40%,animate-mesh-drift 40s
 *   - **错开 animation-delay**(-13s / -27s)让漂移看起来不同步
 *   - 右上角:主题切换按钮(浮于 blob 之上)
 *   - <Outlet /> 居中渲染子页(登录卡 / setup 卡)
 *
 * 注意:浅色模式底色 = background;深色模式 = background(near-black 偏蓝)。blob 透明度
 *      在两个模式下都看着舒服,不需要分模式调。
 */
import { useTheme } from 'next-themes';
import { Outlet } from 'react-router';
import { Moon, Sun, Monitor } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 rounded-full bg-background/40 backdrop-blur-md hover:bg-background/60"
          aria-label="切换主题"
        >
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

/**
 * 三色 mesh blob 背景。
 * fixed inset-0 + pointer-events-none,绝不挡用户交互。
 * 父容器 overflow-hidden 防止 blob 溢出造成横向滚动条。
 */
function MeshBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      {/* indigo blob — 主色,左上 */}
      <div
        className={cn(
          'absolute left-[-10%] top-[-15%] size-[520px] rounded-full opacity-40 blur-3xl',
          'bg-[radial-gradient(circle_at_center,oklch(0.58_0.18_268)_0%,transparent_70%)]',
          'dark:opacity-35',
        )}
        style={{
          animation: 'var(--animate-mesh-drift)',
          animationDelay: '0s',
        }}
      />
      {/* teal blob — 强调,右中 */}
      <div
        className={cn(
          'absolute right-[-8%] top-[20%] size-[480px] rounded-full opacity-35 blur-3xl',
          'bg-[radial-gradient(circle_at_center,oklch(0.69_0.13_188)_0%,transparent_70%)]',
          'dark:opacity-30',
        )}
        style={{
          animation: 'var(--animate-mesh-drift)',
          animationDelay: '-13s',
        }}
      />
      {/* amber blob — 暖色,左下 */}
      <div
        className={cn(
          'absolute bottom-[-15%] left-[15%] size-[500px] rounded-full opacity-30 blur-3xl',
          'bg-[radial-gradient(circle_at_center,oklch(0.78_0.16_75)_0%,transparent_70%)]',
          'dark:opacity-25',
        )}
        style={{
          animation: 'var(--animate-mesh-drift)',
          animationDelay: '-27s',
        }}
      />
    </div>
  );
}

export function PublicLayout() {
  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-background text-foreground">
      <MeshBackground />

      {/* 右上角主题切换 */}
      <div className="fixed right-4 top-4 z-20">
        <ThemeSwitcher />
      </div>

      {/* 主内容居中 */}
      <main className="relative z-10 grid min-h-screen place-items-center px-4 py-12">
        <Outlet />
      </main>
    </div>
  );
}

export default PublicLayout;
