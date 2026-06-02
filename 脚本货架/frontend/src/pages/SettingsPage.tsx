/**
 * 设置页(/settings,登录后可用):
 * - 修改密码卡片:旧密码 + 新密码 + 确认(前端校验两次一致 + ≥6 位),POST /api/auth/change-password。
 * - 外观卡片:主题模式三选一(浅色 / 深色 / 跟随系统),next-themes setTheme。
 * 未登录:显示「请先登录」引导,不崩。
 */
import * as React from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from 'next-themes';
import { ArrowLeft, KeyRound, Laptop, Lock, LogIn, Moon, Palette, Sun } from 'lucide-react';
import { toast } from 'sonner';

import { ApiError } from '@/api/client';
import { useChangePassword } from '@/api/hooks';
import { useAuth } from '@/auth/AuthProvider';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { EmptyState } from '@/components/States';

export function SettingsPage() {
  const { user, isLoading } = useAuth();

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <BackLink />
      <div>
        <h1 className="text-2xl font-bold tracking-tight">设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">管理账号密码与外观偏好。</p>
      </div>

      {/* 外观:登录与否都可用 */}
      <AppearanceCard />

      {/* 修改密码:仅登录后 */}
      {isLoading ? null : user ? (
        <ChangePasswordCard />
      ) : (
        <Card>
          <CardContent className="py-10">
            <EmptyState
              icon={<LogIn className="h-10 w-10" />}
              title="请先登录"
              description="登录后才能修改密码。点击右上角「登录」即可。"
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" />
      返回画廊
    </Link>
  );
}

// ===== 外观 =====
const THEME_OPTIONS = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Laptop },
] as const;

function AppearanceCard() {
  const { theme, setTheme } = useTheme();
  // 避免 SSR/首帧 hydration 不一致:挂载后再读取当前值
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const current = mounted ? theme : undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Palette className="h-4 w-4" />
          外观
        </CardTitle>
        <CardDescription>选择主题模式,设置会记忆在本浏览器。</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {THEME_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const active = current === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setTheme(opt.value)}
                aria-pressed={active}
                className={cn(
                  'flex flex-col items-center justify-center gap-2 rounded-lg border p-4 text-sm font-medium transition-colors',
                  active
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )}
              >
                <Icon className="h-5 w-5" />
                {opt.label}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// ===== 修改密码 =====
function ChangePasswordCard() {
  const changePassword = useChangePassword();
  const [oldPassword, setOldPassword] = React.useState('');
  const [newPassword, setNewPassword] = React.useState('');
  const [confirm, setConfirm] = React.useState('');

  const reset = () => {
    setOldPassword('');
    setNewPassword('');
    setConfirm('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldPassword || !newPassword) {
      toast.error('请填写旧密码和新密码');
      return;
    }
    if (newPassword.length < 6) {
      toast.error('新密码至少 6 位');
      return;
    }
    if (newPassword !== confirm) {
      toast.error('两次输入的新密码不一致');
      return;
    }
    if (newPassword === oldPassword) {
      toast.error('新密码不能与旧密码相同');
      return;
    }
    try {
      await changePassword.mutateAsync({ oldPassword, newPassword });
      toast.success('密码已修改');
      reset();
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        toast.error('旧密码不正确');
      } else if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('修改失败,请重试');
      }
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4" />
          修改密码
        </CardTitle>
        <CardDescription>修改后当前登录保持有效,无需重新登录。</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 隐藏的用户名字段:帮助密码管理器关联账号 */}
          <input type="text" name="username" autoComplete="username" className="hidden" tabIndex={-1} aria-hidden />
          <div className="space-y-2">
            <Label htmlFor="old-password">旧密码</Label>
            <PasswordInput
              id="old-password"
              autoComplete="current-password"
              value={oldPassword}
              onChange={setOldPassword}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">新密码</Label>
            <PasswordInput
              id="new-password"
              autoComplete="new-password"
              value={newPassword}
              onChange={setNewPassword}
            />
            <p className="text-xs text-muted-foreground">至少 6 位。</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">确认新密码</Label>
            <PasswordInput
              id="confirm-password"
              autoComplete="new-password"
              value={confirm}
              onChange={setConfirm}
            />
            {confirm.length > 0 && confirm !== newPassword && (
              <p className="text-xs text-destructive">两次输入不一致。</p>
            )}
          </div>
          <Button type="submit" disabled={changePassword.isPending} className="w-full sm:w-auto">
            {changePassword.isPending ? '提交中…' : '修改密码'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordInput({
  id,
  value,
  autoComplete,
  onChange,
}: {
  id: string;
  value: string;
  autoComplete: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        id={id}
        type="password"
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-9"
      />
    </div>
  );
}
