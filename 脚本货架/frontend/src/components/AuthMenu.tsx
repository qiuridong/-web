/**
 * 右上角鉴权区:
 * - 未登录:显「登录」(若 setup_required 则显「初始化管理员」)。
 * - 已登录:显用户名 + 登出。
 * 登录 / 初始化用同一个 Dialog,按 setupRequired 切换模式。
 */
import * as React from 'react';
import { LogOut, UserRound } from 'lucide-react';
import { toast } from 'sonner';

import { useAuth } from '@/auth/AuthProvider';
import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export function AuthMenu() {
  const { user, setupRequired, login, setup, logout } = useAuth();
  const [open, setOpen] = React.useState(false);

  if (user) {
    return (
      <div className="flex items-center gap-2">
        <span className="hidden items-center gap-1.5 text-sm text-muted-foreground sm:flex">
          <UserRound className="h-4 w-4" />
          {user.display_name || user.username}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await logout();
            toast.success('已登出');
          }}
        >
          <LogOut />
          <span className="hidden sm:inline">登出</span>
        </Button>
      </div>
    );
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        {setupRequired ? '初始化管理员' : '登录'}
      </Button>
      <AuthDialog
        open={open}
        onOpenChange={setOpen}
        mode={setupRequired ? 'setup' : 'login'}
        onLogin={login}
        onSetup={setup}
      />
    </>
  );
}

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  mode: 'login' | 'setup';
  onLogin: (u: string, p: string) => Promise<void>;
  onSetup: (u: string, p: string, displayName?: string) => Promise<void>;
}

function AuthDialog({ open, onOpenChange, mode, onLogin, onSetup }: AuthDialogProps) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [displayName, setDisplayName] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);

  const isSetup = mode === 'setup';

  // 关闭时清空
  React.useEffect(() => {
    if (!open) {
      setPassword('');
      setSubmitting(false);
    }
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.error('请填写用户名和密码');
      return;
    }
    setSubmitting(true);
    try {
      if (isSetup) {
        await onSetup(username.trim(), password, displayName.trim());
        toast.success('管理员已创建并登录');
      } else {
        await onLogin(username.trim(), password);
        toast.success('登录成功');
      }
      onOpenChange(false);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '操作失败,请重试';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isSetup ? '初始化管理员' : '登录'}</DialogTitle>
          <DialogDescription>
            {isSetup
              ? '货架尚未设置管理员,创建首个管理员账号(将自动登录)。'
              : '登录后可上传、编辑、删除脚本与管理标签。'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="auth-username">用户名</Label>
            <Input
              id="auth-username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          {isSetup && (
            <div className="space-y-2">
              <Label htmlFor="auth-display">显示名(可选)</Label>
              <Input
                id="auth-display"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="auth-password">密码</Label>
            <Input
              id="auth-password"
              type="password"
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={submitting} className="w-full sm:w-auto">
              {submitting ? '处理中…' : isSetup ? '创建并登录' : '登录'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
