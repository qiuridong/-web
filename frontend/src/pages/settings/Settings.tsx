/**
 * /settings/:tab — 设置页
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.10。
 *
 * 4 个 tab:账户 / 外观 / 备份 / 关于
 *
 * - 账户:显示当前 user info + 修改密码 + "修改后会话被撤销" 警告
 * - 外观:主题切换(浅/深/system)+ 主题色 picker(简化:6 个预设色)
 * - 备份:导出 zip + 上传恢复 + AlertDialog 二确
 * - 关于:版本 / 后端 OpenAPI / 设计稿路径 / timezone / 主密钥强提示
 *
 * 注:react-colorful 未安装(任务说明可选),改为 6 个预设色 swatch + 写入 CSS var
 */
import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useTheme } from 'next-themes';
import { HexColorPicker, HexColorInput } from 'react-colorful';
import {
  Download,
  KeyRound,
  Loader2,
  LogOut,
  Monitor,
  Moon,
  Palette,
  RotateCcw,
  Save,
  ShieldAlert,
  Sun,
  Upload,
  User,
  TriangleAlert,
  Info,
} from 'lucide-react';
import { toast } from 'sonner';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import PageHeader from '@/components/common/PageHeader';

import { useCurrentUser, useLogout } from '@/api/hooks/auth';
import {
  useBackupExport,
  useBackupImport,
  useChangePassword,
  useSettings,
} from '@/api/hooks/settings';
import { useAuthStore } from '@/stores/auth.store';
import { cn } from '@/lib/utils';

type SettingsTab = 'account' | 'appearance' | 'backup' | 'about';

const TABS: { value: SettingsTab; label: string }[] = [
  { value: 'account', label: '账户' },
  { value: 'appearance', label: '外观' },
  { value: 'backup', label: '备份' },
  { value: 'about', label: '关于' },
];

export function Settings() {
  const params = useParams<{ tab?: string }>();
  const navigate = useNavigate();
  const tab = (params.tab as SettingsTab) ?? 'account';

  function handleChangeTab(v: string) {
    navigate(`/settings/${v}`, { replace: true });
  }

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader title="设置" description="账户、外观、备份与系统信息" />

      <Tabs value={tab} onValueChange={handleChangeTab} className="w-full">
        <TabsList className="h-10 w-full justify-start gap-0.5 rounded-md border-b border-border bg-transparent p-0">
          {TABS.map((t) => (
            <SettingsTabTrigger key={t.value} value={t.value}>
              {t.label}
            </SettingsTabTrigger>
          ))}
        </TabsList>

        <TabsContent value="account" className="mt-5">
          <AccountPanel />
        </TabsContent>
        <TabsContent value="appearance" className="mt-5">
          <AppearancePanel />
        </TabsContent>
        <TabsContent value="backup" className="mt-5">
          <BackupPanel />
        </TabsContent>
        <TabsContent value="about" className="mt-5">
          <AboutPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SettingsTabTrigger({ value, children }: { value: string; children: ReactNode }) {
  return (
    <TabsTrigger
      value={value}
      className={cn(
        'group relative h-10 gap-1.5 rounded-none border-b-2 border-transparent bg-transparent px-3 text-sm font-medium text-muted-foreground transition-colors',
        'data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none',
        'hover:text-foreground',
      )}
    >
      {children}
    </TabsTrigger>
  );
}

/* ============ 账户 ============ */

const pwdSchema = z
  .object({
    old_password: z.string().min(1, '请输入当前密码'),
    new_password: z.string().min(8, '新密码至少 8 位'),
    confirm: z.string().min(1, '请确认新密码'),
  })
  .refine((d) => d.new_password === d.confirm, {
    path: ['confirm'],
    message: '两次密码不一致',
  });
type PwdValues = z.infer<typeof pwdSchema>;

function AccountPanel() {
  const { data: user } = useCurrentUser();
  const change = useChangePassword();
  const logout = useLogout();
  const navigate = useNavigate();
  const clearUser = useAuthStore((s) => s.clearUser);

  const form = useForm<PwdValues>({
    resolver: zodResolver(pwdSchema),
    defaultValues: { old_password: '', new_password: '', confirm: '' },
  });

  async function handlePwdSubmit(values: PwdValues) {
    await change.mutateAsync({
      old_password: values.old_password,
      new_password: values.new_password,
    });
    // 后端文档说明:修改后会话失效;主动登出 + 跳登录
    try {
      await logout.mutateAsync();
    } catch {
      // 即便接口报错也强制清本地态
    }
    clearUser();
    navigate('/login', { replace: true });
  }

  const displayName = user?.display_name || user?.username || '用户';
  const initials = (user?.display_name ?? user?.username ?? 'U').slice(0, 1).toUpperCase();

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-6">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <User className="size-4" strokeWidth={1.75} />
          当前账户
        </h3>
        <div className="flex items-center gap-3">
          <Avatar className="size-12">
            <AvatarFallback className="bg-primary/15 text-base font-semibold text-primary">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-foreground">{displayName}</div>
            <div className="font-mono text-xs text-muted-foreground">@{user?.username}</div>
          </div>
          {user?.is_admin ? (
            <Badge variant="outline" className="ml-auto border-primary/30 bg-primary/10 text-primary">
              管理员
            </Badge>
          ) : null}
        </div>
        <Separator className="my-5" />
        <dl className="space-y-3 text-sm">
          <div className="flex items-baseline justify-between">
            <dt className="text-muted-foreground">上次登录</dt>
            <dd className="font-mono text-xs">{user?.last_login_at ?? '—'}</dd>
          </div>
          <div className="flex items-baseline justify-between">
            <dt className="text-muted-foreground">创建时间</dt>
            <dd className="font-mono text-xs">{user?.created_at ?? '—'}</dd>
          </div>
        </dl>
      </Card>

      <Card className="p-6">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <KeyRound className="size-4" strokeWidth={1.75} />
          修改密码
        </h3>
        <Alert variant="destructive" className="mb-4">
          <ShieldAlert className="size-4" strokeWidth={1.75} />
          <AlertTitle>注意</AlertTitle>
          <AlertDescription>
            修改后所有会话被撤销,需要使用新密码重新登录。
          </AlertDescription>
        </Alert>
        <form
          onSubmit={form.handleSubmit(handlePwdSubmit)}
          className="space-y-4"
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="pwd-old">当前密码</Label>
            <Input
              id="pwd-old"
              type="password"
              autoComplete="current-password"
              {...form.register('old_password')}
              className="h-10"
            />
            {form.formState.errors.old_password ? (
              <p className="text-xs text-danger">
                {form.formState.errors.old_password.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pwd-new">新密码(至少 8 位)</Label>
            <Input
              id="pwd-new"
              type="password"
              autoComplete="new-password"
              {...form.register('new_password')}
              className="h-10"
            />
            {form.formState.errors.new_password ? (
              <p className="text-xs text-danger">
                {form.formState.errors.new_password.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pwd-confirm">确认新密码</Label>
            <Input
              id="pwd-confirm"
              type="password"
              autoComplete="new-password"
              {...form.register('confirm')}
              className="h-10"
            />
            {form.formState.errors.confirm ? (
              <p className="text-xs text-danger">{form.formState.errors.confirm.message}</p>
            ) : null}
          </div>
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? (
              <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
            ) : (
              <Save className="mr-1.5 size-4" strokeWidth={1.75} />
            )}
            修改并重新登录
          </Button>
        </form>
      </Card>
    </div>
  );
}

/* ============ 外观 ============ */

interface PaletteSwatch {
  name: string;
  /** 6 位 hex(react-colorful 输出格式;CSS var 直接接受) */
  hex: string;
}

const SWATCHES: PaletteSwatch[] = [
  { name: 'Indigo', hex: '#5865F2' },
  { name: 'Teal', hex: '#0E9F8B' },
  { name: 'Emerald', hex: '#10B981' },
  { name: 'Rose', hex: '#F43F5E' },
  { name: 'Amber', hex: '#F59E0B' },
  { name: 'Violet', hex: '#8B5CF6' },
];

/** 默认 indigo,与 index.css 的 OKLCH 视觉对齐 */
const DEFAULT_HEX = '#5865F2';

const PALETTE_HEX_KEY = 'signin-panel-palette-hex';
const STYLE_ID = 'theme-overrides';

/**
 * 把 hex 写入 CSS var,直接覆盖 oklch 定义。
 *
 * shadcn / Tailwind v4 的 CSS var 接受任意 CSS 颜色,所以 hex 也行;
 * --ring 派生半透明(注:hex 不支持透明度,用 color-mix 让 ring 自动取 50%)。
 *
 * 传 null 清除自定义(回到 index.css 默认)。
 */
function applyHexPalette(hex: string | null) {
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement('style');
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  if (!hex) {
    el.textContent = '';
    return;
  }
  el.textContent = `:root, .dark {
  --primary: ${hex};
  --ring: color-mix(in oklch, ${hex} 50%, transparent);
  --chart-1: ${hex};
  --sidebar-primary: ${hex};
  --sidebar-ring: color-mix(in oklch, ${hex} 50%, transparent);
}`;
}

function loadInitialHex(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(PALETTE_HEX_KEY);
  } catch {
    return null;
  }
}

/** 大小写无关 hex 等值比较 */
function sameHex(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return a.toLowerCase() === b.toLowerCase();
}

function AppearancePanel() {
  const { theme, setTheme } = useTheme();
  // 初值:localStorage 自定义 hex(可能与 swatch 对齐,也可能是任意值)
  const [hex, setHex] = useState<string | null>(loadInitialHex);
  // picker 当前色(用户拖拽时用,提交才落 localStorage)
  const [pickerHex, setPickerHex] = useState<string>(hex ?? DEFAULT_HEX);

  // 启动时应用
  useEffect(() => {
    if (hex) applyHexPalette(hex);
  }, [hex]);

  function persistHex(next: string | null) {
    setHex(next);
    try {
      if (next) localStorage.setItem(PALETTE_HEX_KEY, next);
      else localStorage.removeItem(PALETTE_HEX_KEY);
    } catch {
      // ignore quota
    }
    applyHexPalette(next);
  }

  function chooseSwatch(swatchHex: string) {
    setPickerHex(swatchHex);
    persistHex(swatchHex);
    const sw = SWATCHES.find((s) => sameHex(s.hex, swatchHex));
    toast.success(sw ? `已切换主题色为 ${sw.name}` : `已应用自定义色 ${swatchHex}`);
  }

  function commitPicker() {
    persistHex(pickerHex);
    toast.success(`已应用自定义色 ${pickerHex}`);
  }

  function resetDefault() {
    setPickerHex(DEFAULT_HEX);
    persistHex(null);
    toast.success('已恢复默认 Indigo');
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-6">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Sun className="size-4" strokeWidth={1.75} />
          主题模式
        </h3>
        <RadioGroup value={theme ?? 'system'} onValueChange={(v) => setTheme(v)}>
          <ThemeRadio value="light" icon={Sun} label="浅色" />
          <ThemeRadio value="dark" icon={Moon} label="深色" />
          <ThemeRadio value="system" icon={Monitor} label="跟随系统" />
        </RadioGroup>
      </Card>

      <Card className="p-6">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Palette className="size-4" strokeWidth={1.75} />
          主题色
        </h3>
        <p className="mb-4 text-xs text-muted-foreground">
          自动写入 CSS 变量 (--primary / --ring / --chart-1),刷新后保持。
        </p>

        {/* 快捷预设 */}
        <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
          快捷预设
        </div>
        <div className="mb-5 grid grid-cols-3 gap-2 sm:grid-cols-6">
          {SWATCHES.map((s) => {
            const selected = sameHex(hex, s.hex);
            return (
              <button
                key={s.name}
                type="button"
                onClick={() => chooseSwatch(s.hex)}
                title={`${s.name} · ${s.hex}`}
                className={cn(
                  'group flex flex-col items-center gap-1 rounded-lg border p-2 transition-colors',
                  selected ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/40',
                )}
              >
                <span
                  className="block size-8 rounded-md shadow-sm"
                  style={{ background: s.hex }}
                  aria-hidden
                />
                <span className="text-[11px] font-medium">{s.name}</span>
              </button>
            );
          })}
        </div>

        {/* 自定义 picker */}
        <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
          自定义
        </div>
        <div className="grid gap-3 sm:grid-cols-[200px_1fr]">
          <div className="flex justify-center">
            <HexColorPicker
              color={pickerHex}
              onChange={setPickerHex}
              style={{ width: 180, height: 140 }}
            />
          </div>
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2">
              <span
                className="block size-8 shrink-0 rounded-md border border-border shadow-sm"
                style={{ background: pickerHex }}
                aria-hidden
              />
              <HexColorInput
                color={pickerHex}
                onChange={setPickerHex}
                prefixed
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 font-mono text-sm uppercase tabular-nums text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={commitPicker}>
                <Save className="mr-1.5 size-4" strokeWidth={1.75} />
                应用
              </Button>
              <Button variant="outline" size="sm" onClick={resetDefault}>
                <RotateCcw className="mr-1.5 size-4" strokeWidth={1.75} />
                恢复默认 Indigo
              </Button>
            </div>
            {hex ? (
              <p className="text-[11px] text-muted-foreground">
                当前生效:
                <code className="ml-1 font-mono uppercase tracking-wide">{hex}</code>
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">使用主题内置默认色</p>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

function ThemeRadio({
  value,
  icon: Icon,
  label,
}: {
  value: string;
  icon: typeof Sun;
  label: string;
}) {
  return (
    <Label
      htmlFor={`theme-${value}`}
      className="flex cursor-pointer items-center gap-3 rounded-md border border-border p-3 hover:bg-accent/50"
    >
      <RadioGroupItem value={value} id={`theme-${value}`} />
      <Icon className="size-4" strokeWidth={1.75} />
      <span className="text-sm font-medium">{label}</span>
    </Label>
  );
}

/* ============ 备份 ============ */

function BackupPanel() {
  const exportMut = useBackupExport();
  const importMut = useBackupImport();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(true);

  function pickFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    if (f) {
      setPendingFile(f);
    }
  }

  async function handleConfirmImport() {
    if (!pendingFile) return;
    await importMut.mutateAsync({ file: pendingFile, overwrite });
    setPendingFile(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-6">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Download className="size-4" strokeWidth={1.75} />
          导出备份
        </h3>
        <p className="mb-4 text-sm text-muted-foreground">
          一键导出 <code className="font-mono">db.sqlite3</code> +{' '}
          <code className="font-mono">encryption.key</code> + meta.json 为 zip。
        </p>
        <Button size="lg" onClick={() => exportMut.mutate()} disabled={exportMut.isPending}>
          {exportMut.isPending ? (
            <Loader2 className="mr-2 size-4 animate-spin" strokeWidth={1.75} />
          ) : (
            <Download className="mr-2 size-4" strokeWidth={1.75} />
          )}
          立即下载备份
        </Button>
      </Card>

      <Card className="p-6">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Upload className="size-4" strokeWidth={1.75} />
          恢复备份
        </h3>
        <Alert variant="destructive" className="mb-4">
          <TriangleAlert className="size-4" strokeWidth={1.75} />
          <AlertTitle>谨慎操作</AlertTitle>
          <AlertDescription>
            将覆盖当前数据并可能触发服务重启 / 调度器重置。建议先导出当前备份。
          </AlertDescription>
        </Alert>
        <label
          htmlFor="backup-file"
          className="flex h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-border bg-card/30 text-sm text-muted-foreground transition-colors hover:bg-card/50"
        >
          <Upload className="size-5" strokeWidth={1.75} />
          {pendingFile ? (
            <>
              <span className="font-mono text-xs text-foreground">{pendingFile.name}</span>
              <span className="text-[11px]">
                {(pendingFile.size / 1024).toFixed(1)} KiB · 点击下方确认或重新选择
              </span>
            </>
          ) : (
            <>
              <span>点击或拖拽 .zip 文件至此</span>
            </>
          )}
          <input
            ref={inputRef}
            id="backup-file"
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={pickFile}
          />
        </label>
        <div className="mt-3 flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            id="overwrite"
            checked={overwrite}
            onChange={(e) => setOverwrite(e.target.checked)}
            className="size-3.5"
          />
          <Label htmlFor="overwrite" className="text-xs font-normal text-muted-foreground">
            覆盖现有数据(默认开启)
          </Label>
        </div>
      </Card>

      <AlertDialog
        open={!!pendingFile && !importMut.isPending}
        onOpenChange={(o) => {
          if (!o) setPendingFile(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <TriangleAlert className="size-5 text-danger" strokeWidth={1.75} />
              确认从备份「{pendingFile?.name}」恢复?
            </AlertDialogTitle>
            <AlertDialogDescription>
              将{overwrite ? '覆盖' : '合并到'}当前 DB / 主密钥;调度器会重置;
              当前登录可能失效。建议先导出当前备份。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={importMut.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={importMut.isPending}
              onClick={(e) => {
                e.preventDefault();
                void handleConfirmImport();
              }}
            >
              {importMut.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Upload className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认恢复
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/* ============ 关于 ============ */

function AboutPanel() {
  const { data: settings } = useSettings();
  const tz = (settings?.timezone?.value as string | undefined) ?? 'Asia/Shanghai';

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-6">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Info className="size-4" strokeWidth={1.75} />
          系统信息
        </h3>
        <dl className="space-y-3 text-sm">
          <AboutRow label="应用版本" value="0.1.0" />
          <AboutRow label="时区" value={tz} mono />
          <AboutRow
            label="后端 OpenAPI"
            value={
              <a
                href="/openapi.json"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                /openapi.json
              </a>
            }
          />
          <AboutRow label="设计稿(本地)" value="进度/设计/" mono />
          <AboutRow label="构建产物" value="frontend/dist" mono />
        </dl>
      </Card>

      <Card className="p-6">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <ShieldAlert className="size-4 text-danger" strokeWidth={1.75} />
          主密钥(异地备份)
        </h3>
        <Alert variant="destructive">
          <KeyRound className="size-4" strokeWidth={1.75} />
          <AlertTitle>data/encryption.key 必须异地备份</AlertTitle>
          <AlertDescription className="space-y-2 text-xs">
            <p>
              所有 secret 字段、apprise URL 都用此密钥加密落库。
              <strong className="ml-1 text-foreground">密钥丢失 = 所有加密配置作废</strong>。
            </p>
            <p>
              建议把 <code className="font-mono">data/encryption.key</code> 拷贝到至少 2 个独立位置
              (云盘 + U盘),并定期验证可恢复。
            </p>
          </AlertDescription>
        </Alert>
      </Card>

      <Card className="col-span-full p-6">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <LogOut className="size-4" strokeWidth={1.75} />
          快捷
        </h3>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <a href="/openapi.json" target="_blank" rel="noopener noreferrer">
              查看 API 契约
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href="/" target="_self">
              返回首页
            </a>
          </Button>
        </div>
      </Card>
    </div>
  );
}

function AboutRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn('truncate text-right text-foreground', mono && 'font-mono text-xs')}>
        {value}
      </dd>
    </div>
  );
}

export default Settings;
