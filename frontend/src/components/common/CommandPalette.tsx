/**
 * <CommandPalette> — ⌘K 全局命令面板
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.11。
 *
 * 控制:`useUIStore.commandPaletteOpen`
 * 快捷键:⌘K / Ctrl+K 切换;Esc 关闭(cmdk 自带)
 *
 * 命令:
 *   - 扫描脚本
 *   - 跳转:仪表盘 / 脚本 / 通知 / 设置
 *   - 切换主题:浅 / 深 / system
 *   - 登出
 *   - 动态:已有脚本列表(点击跳详情)
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useTheme } from 'next-themes';
import {
  Bell,
  LayoutDashboard,
  LogOut,
  Monitor,
  Moon,
  RefreshCw,
  ScrollText,
  Settings,
  Sun,
} from 'lucide-react';
import { toast } from 'sonner';

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command';

import { useUIStore } from '@/stores/ui.store';
import { useAuthStore } from '@/stores/auth.store';
import { useLogout } from '@/api/hooks/auth';
import { useScanScripts, useScripts } from '@/api/hooks/scripts';

export function CommandPalette() {
  const open = useUIStore((s) => s.commandPaletteOpen);
  const setOpen = useUIStore((s) => s.setCommandPalette);
  const navigate = useNavigate();
  const { setTheme } = useTheme();
  const scan = useScanScripts();
  const logout = useLogout();
  const clearUser = useAuthStore((s) => s.clearUser);
  const { data: scripts } = useScripts();

  // ⌘K / Ctrl+K 全局热键
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  function go(path: string) {
    setOpen(false);
    navigate(path);
  }

  async function handleLogout() {
    setOpen(false);
    try {
      await logout.mutateAsync();
    } catch {
      // ignore
    }
    clearUser();
    toast.success('已退出登录');
    navigate('/login', { replace: true });
  }

  function handleScan() {
    setOpen(false);
    scan.mutate();
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="搜索命令、脚本、跳转…" />
      <CommandList>
        <CommandEmpty>无匹配</CommandEmpty>
        <CommandGroup heading="导航">
          <CommandItem onSelect={() => go('/dashboard')}>
            <LayoutDashboard />
            <span>仪表盘</span>
            <CommandShortcut>G D</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => go('/scripts')}>
            <ScrollText />
            <span>脚本</span>
            <CommandShortcut>G S</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => go('/notifications')}>
            <Bell />
            <span>通知</span>
            <CommandShortcut>G N</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => go('/settings')}>
            <Settings />
            <span>设置</span>
            <CommandShortcut>G ,</CommandShortcut>
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="操作">
          <CommandItem onSelect={handleScan} disabled={scan.isPending}>
            <RefreshCw />
            <span>扫描脚本</span>
          </CommandItem>
          <CommandItem onSelect={() => setTheme('light')}>
            <Sun />
            <span>切换为浅色主题</span>
          </CommandItem>
          <CommandItem onSelect={() => setTheme('dark')}>
            <Moon />
            <span>切换为深色主题</span>
          </CommandItem>
          <CommandItem onSelect={() => setTheme('system')}>
            <Monitor />
            <span>跟随系统主题</span>
          </CommandItem>
          <CommandItem onSelect={handleLogout} disabled={logout.isPending}>
            <LogOut />
            <span>退出登录</span>
          </CommandItem>
        </CommandGroup>
        {scripts && scripts.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="脚本">
              {scripts.slice(0, 20).map((s) => (
                <CommandItem
                  key={s.slug}
                  value={`${s.name} ${s.slug}`}
                  onSelect={() => go(`/scripts/${s.slug}`)}
                >
                  <ScrollText />
                  <div className="flex flex-col">
                    <span>{s.name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{s.slug}</span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}
      </CommandList>
    </CommandDialog>
  );
}

export default CommandPalette;
