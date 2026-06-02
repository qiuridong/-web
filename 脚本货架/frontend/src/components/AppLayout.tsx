import { Link, Outlet } from 'react-router-dom';

import { AuthMenu } from '@/components/AuthMenu';
import { ThemeToggle } from '@/components/ThemeToggle';

/** 全站外壳:吸顶玻璃顶栏 + 路由 outlet。 */
export function AppLayout() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="glass sticky top-0 z-40 border-b">
        <div className="container flex h-14 items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/shelf.svg" alt="" className="h-7 w-7" />
            <span className="text-base font-semibold tracking-tight">脚本货架</span>
          </Link>
          <div className="flex items-center gap-1.5">
            <ThemeToggle />
            <AuthMenu />
          </div>
        </div>
      </header>
      <main className="container py-6 sm:py-8">
        <Outlet />
      </main>
      <footer className="container py-8 text-center text-xs text-muted-foreground">
        脚本货架 · 集中展示与管理签到脚本,一键导入
        <a
          href="https://jb.aijiaxia.cc"
          target="_blank"
          rel="noreferrer"
          className="ml-1 text-primary hover:underline"
        >
          签到管家
        </a>
      </footer>
    </div>
  );
}
