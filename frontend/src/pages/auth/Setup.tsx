/**
 * /setup — 首次安装向导
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.2(初始化页)。
 *
 * 视觉:与登录卡同款 glass,稍宽 480px。
 * 关键警示:醒目的 <Alert variant="warning"> 提示主密钥已生成,完成后立即去备份。
 * 字段:username / password / display_name(可选) / "我已了解" checkbox(必勾才能提交)。
 *
 * 行为:
 *   - useSetupStatus:needs_setup=false → 立即 redirect /login(防 setup 重复触发)
 *   - useSetup 成功 → 后端自动登录返回 user → setUser → navigate /dashboard
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Loader2,
  AlertCircle,
  KeyRound,
  ShieldAlert,
  CheckCircle2,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { useSetup, useSetupStatus, meToAuthUser } from '@/api/hooks/auth';
import { useAuthStore } from '@/stores/auth.store';
import { formatError } from '@/lib/error';
import { cn } from '@/lib/utils';

const setupSchema = z
  .object({
    username: z
      .string()
      .min(3, { message: '用户名至少 3 个字符' })
      .max(64, { message: '用户名过长' })
      .regex(/^[A-Za-z0-9_.-]+$/, {
        message: '只允许字母、数字、下划线、点、横线',
      }),
    password: z
      .string()
      .min(8, { message: '密码至少 8 个字符' })
      .max(256, { message: '密码过长' }),
    confirmPassword: z.string(),
    displayName: z
      .string()
      .max(64, { message: '显示名过长' })
      .optional()
      .or(z.literal('')),
    acknowledged: z.literal(true, {
      errorMap: () => ({ message: '请先勾选确认' }),
    }),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: '两次密码不一致',
    path: ['confirmPassword'],
  });

type SetupForm = z.infer<typeof setupSchema>;

/** 密码强度粗评:返回 0..4(0 弱 → 4 强) */
function gradePassword(pw: string): number {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 8) s += 1;
  if (pw.length >= 12) s += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s += 1;
  if (/\d/.test(pw)) s += 1;
  if (/[^A-Za-z0-9]/.test(pw)) s += 1;
  return Math.min(s, 4);
}

const STRENGTH_LABELS = ['', '太弱', '一般', '良好', '强'];
const STRENGTH_COLORS = [
  'bg-muted',
  'bg-danger',
  'bg-warning',
  'bg-info',
  'bg-success',
];

export function SetupPage() {
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  // 已经初始化过 → 不该在 setup 页;静默跳 /login
  const { data: setupStatus, isLoading: statusLoading } = useSetupStatus();
  useEffect(() => {
    if (setupStatus && !setupStatus.needs_setup) {
      navigate('/login', { replace: true });
    }
  }, [setupStatus, navigate]);

  const { mutateAsync: setup, isPending } = useSetup();
  const setUser = useAuthStore((s) => s.setUser);

  const form = useForm<SetupForm>({
    resolver: zodResolver(setupSchema),
    defaultValues: {
      username: 'admin',
      password: '',
      confirmPassword: '',
      displayName: '',
      acknowledged: false as unknown as true,
    },
  });

  const pwValue = form.watch('password');
  const strength = gradePassword(pwValue);

  async function onSubmit(values: SetupForm) {
    setFormError(null);
    try {
      const res = await setup({
        username: values.username.trim(),
        password: values.password,
        ...(values.displayName
          ? { display_name: values.displayName.trim() }
          : {}),
      });
      setUser(meToAuthUser(res.user));
      toast.success('已创建管理员并登录');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const msg = formatError(err);
      setFormError(msg);
    }
  }

  // 还在拿 setup-status,占位骨架(避免短闪)
  if (statusLoading) {
    return (
      <Card className="glass w-[480px] max-w-[calc(100vw-2rem)] rounded-2xl border-border/60 shadow-xl">
        <CardContent className="flex items-center justify-center py-20 text-sm text-muted-foreground">
          <Loader2 size={16} className="mr-2 animate-spin" strokeWidth={1.75} />
          检测初始化状态…
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        'glass relative w-[480px] max-w-[calc(100vw-2rem)] rounded-2xl border-border/60',
        'shadow-xl',
      )}
    >
      <CardHeader className="space-y-3 pb-4 pt-8 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md">
          <KeyRound size={22} strokeWidth={1.75} />
        </div>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            创建管理员账户
          </h1>
          <p className="text-sm text-muted-foreground">
            首次安装 ·
            <span className="ml-1 font-medium text-foreground">签到管家</span>
          </p>
        </div>
      </CardHeader>

      <CardContent className="px-8 pb-8 pt-2">
        <Alert
          className={cn(
            'mb-5 border-warning/40 bg-warning/8 text-warning-foreground',
            'dark:bg-warning/8',
          )}
        >
          <ShieldAlert size={14} strokeWidth={1.75} className="text-warning" />
          <AlertTitle className="text-sm font-semibold text-foreground">
            主密钥已生成
          </AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">
            后端已在 <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">data/encryption.key</code> 写入唯一加密主密钥。
            创建账户后,请立即前往
            <span className="mx-1 font-medium text-foreground">设置 → 备份</span>
            导出并离线保存,**密钥丢失即所有加密配置不可恢复**。
          </AlertDescription>
        </Alert>

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
                      placeholder="admin"
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
              name="displayName"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-sm font-medium">
                    显示名
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      (可选)
                    </span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="例如:管理员"
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
                      autoComplete="new-password"
                      placeholder="至少 8 位"
                      className="h-10"
                      disabled={isPending}
                      {...field}
                    />
                  </FormControl>
                  {/* 强度指示(4 段) */}
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex flex-1 gap-1">
                      {[1, 2, 3, 4].map((i) => (
                        <span
                          key={i}
                          className={cn(
                            'h-1 flex-1 rounded-full transition-colors',
                            i <= strength
                              ? STRENGTH_COLORS[strength]
                              : 'bg-muted',
                          )}
                        />
                      ))}
                    </div>
                    <span className="w-10 text-right text-[10px] tabular-nums text-muted-foreground">
                      {STRENGTH_LABELS[strength]}
                    </span>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="confirmPassword"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-sm font-medium">
                    确认密码
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      autoComplete="new-password"
                      placeholder="再次输入密码"
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
              name="acknowledged"
              render={({ field }) => (
                <FormItem className="rounded-md border border-border/60 bg-muted/30 p-3">
                  <div className="flex items-start gap-2">
                    <FormControl>
                      <Checkbox
                        checked={field.value === true}
                        onCheckedChange={(v) =>
                          field.onChange(v === true ? true : false)
                        }
                        disabled={isPending}
                        id="acknowledged"
                        className="mt-0.5"
                      />
                    </FormControl>
                    <Label
                      htmlFor="acknowledged"
                      className="cursor-pointer text-xs font-normal leading-relaxed text-foreground"
                    >
                      我已了解 — 主密钥丢失或泄露后,所有加密配置(脚本 cookie / 推送
                      token 等)将无法恢复,需重置数据库。完成创建后会立即去备份。
                    </Label>
                  </div>
                  <FormMessage className="mt-1.5" />
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
                  <span>创建中…</span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} strokeWidth={1.75} />
                  <span>创建管理员</span>
                </>
              )}
            </Button>
          </form>
        </Form>

        <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
          <span className="tabular-nums">v0.1.0</span>
          <Link
            to="/login"
            className="rounded px-1.5 py-0.5 transition-colors hover:bg-accent hover:text-foreground"
          >
            已有账户 · 去登录
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

export default SetupPage;
