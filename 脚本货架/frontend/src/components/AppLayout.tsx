import * as React from 'react';
import { Link, Outlet } from 'react-router-dom';
import { Settings2 } from 'lucide-react';

import { AuthMenu } from '@/components/AuthMenu';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';
import { ManagerSettingsDialog } from '@/components/ManagerSettings';

/** 全站外壳:吸顶玻璃顶栏 + 路由 outlet。 */
export function AppLayout() {
  const [mgrOpen, setMgrOpen] = React.useState(false);
  return (
    <div className="min-h-dvh bg-background">
      <header className="glass sticky top-0 z-40 border-b">
        <div className="container flex h-14 items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/shelf.svg" alt="" className="h-7 w-7" />
            <span className="text-base font-semibold tracking-tight">脚本货架</span>
          </Link>
          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMgrOpen(true)}
              title="设置我的管家地址"
              aria-label="设置我的管家地址"
            >
              <Settings2 className="h-4 w-4" />
            </Button>
            <ThemeToggle />
            <AuthMenu />
          </div>
        </div>
      </header>
      <main className="container py-6 sm:py-8">
        <Outlet />
      </main>
      <footer className="container py-8 text-center text-xs text-muted-foreground">
        脚本货架 · 集中展示与管理签到脚本,一键导入到你自己的
        <button onClick={() => setMgrOpen(true)} className="ml-1 text-primary hover:underline">
          签到管家
        </button>
      </footer>
      <ManagerSettingsDialog open={mgrOpen} onOpenChange={setMgrOpen} />
    </div>
  );
}
