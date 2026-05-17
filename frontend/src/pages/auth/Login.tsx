/**
 * /login — 玻璃拟态登录页
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.1(登录页 wireframe + 美化要点)。
 *
 * 视觉关键:
 *   - 卡片宽 400px、rounded-2xl、p-8、`.glass` 玻璃拟态(70% 白 / 60% 深底 + 20px blur)
 *   - 标题 text-2xl font-semibold tracking-tight
 *   - input h-10 rounded-md
 *   - 提交按钮 w-full h-10 主色 + loading 时 Loader2 旋转
 *   - 30 天免登录 checkbox(占位,后端字段 'remember_me' 暂未实现,UI 先建好)
 *
 * 行为:
 *   - react-hook-form + zod
 *   - 提交调 useLogin → 成功 navigate(from ?? '/dashboard')
 *   - 失败:sonner toast + 表单底部 Alert
 *   - URL ?from=/some/path 用于登录后回跳
 *
 * 关于自动检测 setup:暂时本页不主动检测 setup-status 跳 /setup,
 * 由 PublicLayout 的 loader(批次后续接入)或 router 守卫处理;现阶段两个页面互相独立。
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, AlertCircle, LogIn } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { useLogin, useSetupStatus, meToAuthUser } from '@/api/hooks/auth';
import { useAuthStore } from '@/stores/auth.store';
import { formatError } from '@/lib/error';
import { cn } from '@/lib/utils';

const loginSchema = z.object({
  username: z
    .string()
    .min(1, { message: '请输入用户名' })
    .max(64, { message: '用户名过长' }),
  password: z
    .string()
    .min(1, { message: '请输入密码' })
    .max(256, { message: '密码过长' }),
  rememberMe: z.boolean().default(false).optional(),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);

  // 静默检测:首屏若未初始化 → 跳 /setup
  const { data: setupStatus } = useSetupStatus();
  useEffect(() => {
    if (setupStatus?.needs_setup) {
      navigate('/setup', { replace: true });
    }
  }, [setupStatus, navigate]);

  const { mutateAsync: login, isPending } = useLogin();
  const setUser = useAuthStore((s) => s.setUser);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: '',
      password: '',
      rememberMe: false,
    },
  });

  async function onSubmit(values: LoginForm) {
    setFormError(null);
    try {
      const res = await login({
        username: values.username,
        password: values.password,
      });
      setUser(meToAuthUser(res.user));
      toast.success(`欢迎回来,${res.user.display_name || res.user.username}`);
      const from = params.get('from') || '/dashboard';
      navigate(from, { replace: true });
    } catch (err) {
      const msg = formatError(err);
      setFormError(msg);
      // mutation onError 已全局 toast,这里不再重复 toast
    }
  }

  return (
    <Card
      className={cn(
        'glass relative w-[400px] max-w-[calc(100vw-2rem)] rounded-2xl border-border/60',
        'shadow-xl',
      )}
    >
      <CardHeader className="space-y-3 pb-4 pt-8 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md">
          <span className="text-xl font-bold tracking-tight">签</span>
        </div>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            欢迎回来
          </h1>
          <p className="text-sm text-muted-foreground">
            登录到 <span className="font-medium text-foreground">签到管家</span>
          </p>
        </div>
      </CardHeader>

      <CardContent className="px-8 pb-8 pt-2">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-sm font-medium">
                    用户名
                  </FormLabel>
                  <FormControl>
                    <Input
                      autoComplete="username"
                      autoFocus
                      placeholder="管理员账号"
                      className="h-10"
                      disabled={isPending}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-sm font-medium">密码</FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      autoComplete="current-password"
                      placeholder="••••••••"
                      className="h-10"
                      disabled={isPending}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="rememberMe"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center gap-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      disabled={isPending}
                      id="rememberMe"
                    />
                  </FormControl>
                  <Label
                    htmlFor="rememberMe"
                    className="cursor-pointer text-xs font-normal text-muted-foreground"
                  >
                    30 天内自动登录
                  </Label>
                </FormItem>
              )}
            />

            {formError ? (
              <Alert variant="destructive" className="py-3">
                <AlertCircle size={14} strokeWidth={1.75} />
                <AlertDescription className="text-xs">
                  {formError}
                </AlertDescription>
              </Alert>
            ) : null}

            <Button
              type="submit"
              disabled={isPending}
              className="h-10 w-full gap-2"
            >
              {isPending ? (
                <>
                  <Loader2 size={16} strokeWidth={1.75} className="animate-spin" />
                  <span>登录中…</span>
                </>
              ) : (
                <>
                  <LogIn size={16} strokeWidth={1.75} />
                  <span>登 录</span>
                </>
              )}
            </Button>
          </form>
        </Form>

        <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
          <span className="tabular-nums">v0.1.0</span>
          <Link
            to="/setup"
            className="rounded px-1.5 py-0.5 transition-colors hover:bg-accent hover:text-foreground"
          >
            首次安装?
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

export default LoginPage;
