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
  Image as ImageIcon,
  KeyRound,
  Loader2,
  LogOut,
  Monitor,
  Moon,
  Palette,
  RotateCcw,
  Save,
  ShieldAlert,
  Sparkles,
  Sun,
  Upload,
  User,
  TriangleAlert,
  Trash2,
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
  BACKGROUND_PRESETS,
  DEFAULT_APPEARANCE,
  fileToDataUrl,
  useAppearance,
  useUpdateAppearance,
  type AppearanceData,
} from '@/api/hooks/appearance';
import {
  useBackupExport,
  useBackupImport,
  useChangePassword,
  useSettings,
} from '@/api/hooks/settings';
import { Slider } from '@/components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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

      <div className="lg:col-span-2">
        <BrandingCard />
      </div>

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

/* ============ 品牌与背景 ============ */

const BLEND_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: 'normal', label: '默认 (Normal)' },
  { value: 'multiply', label: '正片叠底 (Multiply)' },
  { value: 'screen', label: '滤色 (Screen)' },
  { value: 'overlay', label: '叠加 (Overlay)' },
  { value: 'darken', label: '变暗 (Darken)' },
  { value: 'lighten', label: '变亮 (Lighten)' },
  { value: 'soft-light', label: '柔光 (Soft Light)' },
  { value: 'hard-light', label: '强光 (Hard Light)' },
];

function BrandingCard() {
  const { data: remote, isLoading } = useAppearance();
  const update = useUpdateAppearance();

  // 本地编辑态(用户改后还没保存的草稿)
  const [draft, setDraft] = useState<AppearanceData>(DEFAULT_APPEARANCE);
  const [logoUploading, setLogoUploading] = useState(false);
  const [bgUploading, setBgUploading] = useState(false);

  // remote 拿到后同步到 draft(只在初次加载或 remote 更新时)
  useEffect(() => {
    if (remote) setDraft(remote);
  }, [remote]);

  const logoFileRef = useRef<HTMLInputElement | null>(null);
  const bgFileRef = useRef<HTMLInputElement | null>(null);

  async function handleLogoPick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = ''; // 允许重选同一文件
    if (!f) return;
    setLogoUploading(true);
    try {
      const dataUrl = await fileToDataUrl(f, 1 * 1024 * 1024); // logo 上限 1 MB
      setDraft((d) => ({ ...d, logo_image_data_url: dataUrl }));
      toast.success(`Logo 已加载(${(f.size / 1024).toFixed(0)} KB),记得点保存`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLogoUploading(false);
    }
  }

  async function handleBgPick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    setBgUploading(true);
    try {
      const dataUrl = await fileToDataUrl(f, 2 * 1024 * 1024); // 背景图 2 MB
      setDraft((d) => ({ ...d, background_image_data_url: dataUrl }));
      toast.success(`背景图已加载(${(f.size / 1024).toFixed(0)} KB),记得点保存`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载失败');
    } finally {
      setBgUploading(false);
    }
  }

  function clearLogo() {
    setDraft((d) => ({ ...d, logo_image_data_url: '' }));
  }
  function clearBackground() {
    setDraft((d) => ({ ...d, background_image_data_url: '' }));
  }

  function handleSave() {
    update.mutate(draft);
  }

  function handleReset() {
    setDraft(DEFAULT_APPEARANCE);
    update.mutate(DEFAULT_APPEARANCE);
  }

  const dirty = !!remote && JSON.stringify(draft) !== JSON.stringify(remote);

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Sparkles className="size-4" strokeWidth={1.75} />
          品牌与背景
        </h3>
        {dirty ? (
          <Badge variant="outline" className="border-warning/30 bg-warning/10 text-warning">
            未保存
          </Badge>
        ) : null}
      </div>
      <p className="mb-5 text-xs text-muted-foreground">
        网站标题 / 侧栏 Logo / 全局背景图。图片以 base64 内联存(Logo &lt; 1 MB,背景图 &lt; 2 MB)。
      </p>

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
          加载中…
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {/* 左列:文本设置 */}
          <div className="space-y-3.5">
            <div className="space-y-1.5">
              <Label htmlFor="appearance-title" className="text-xs">
                网站标题(浏览器 tab + 侧栏)
              </Label>
              <Input
                id="appearance-title"
                value={draft.site_title}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, site_title: e.target.value }))
                }
                placeholder="签到管家"
                className="h-9"
                maxLength={128}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="appearance-subtitle" className="text-xs">
                副标题(侧栏品牌名下方小字,可空)
              </Label>
              <Input
                id="appearance-subtitle"
                value={draft.site_subtitle}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, site_subtitle: e.target.value }))
                }
                placeholder="例如 v0.1.0 / Beta"
                className="h-9"
                maxLength={128}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="appearance-logo-text" className="text-xs">
                侧栏 Logo 文本(无图时显示,1-2 字符)
              </Label>
              <Input
                id="appearance-logo-text"
                value={draft.sidebar_logo_text}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, sidebar_logo_text: e.target.value }))
                }
                placeholder="签"
                className="h-9 max-w-24 text-center font-bold"
                maxLength={8}
              />
            </div>

            {/* Logo 图上传 */}
            <div className="space-y-1.5">
              <Label className="text-xs">
                Logo 图片(可选,覆盖文本)
              </Label>
              <div className="flex items-center gap-3">
                <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
                  {draft.logo_image_data_url ? (
                    <img
                      src={draft.logo_image_data_url}
                      alt="logo preview"
                      className="size-full object-cover"
                    />
                  ) : (
                    <ImageIcon className="size-5 text-muted-foreground" strokeWidth={1.75} />
                  )}
                </div>
                <div className="flex flex-1 flex-wrap items-center gap-2">
                  <input
                    ref={logoFileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleLogoPick}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5"
                    onClick={() => logoFileRef.current?.click()}
                    disabled={logoUploading}
                  >
                    {logoUploading ? (
                      <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
                    ) : (
                      <Upload className="size-3.5" strokeWidth={1.75} />
                    )}
                    {draft.logo_image_data_url ? '更换' : '上传'}
                  </Button>
                  {draft.logo_image_data_url ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 gap-1.5 text-danger"
                      onClick={clearLogo}
                    >
                      <Trash2 className="size-3.5" strokeWidth={1.75} />
                      清除
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          {/* 右列:背景图设置 */}
          <div className="space-y-3.5">
            {/* 预设背景快捷选择(无需上传) */}
            <div className="space-y-1.5">
              <Label className="text-xs">快捷预设(一键应用,无需上传)</Label>
              <div className="grid grid-cols-6 gap-1.5">
                {BACKGROUND_PRESETS.map((p) => {
                  const selected = draft.background_image_data_url === p.dataUrl;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() =>
                        setDraft((d) => ({
                          ...d,
                          background_image_data_url: p.dataUrl,
                        }))
                      }
                      title={p.name}
                      className={cn(
                        'group relative aspect-square overflow-hidden rounded-md border-2 transition-all',
                        selected
                          ? 'border-primary ring-2 ring-primary/30'
                          : 'border-border hover:border-primary/50',
                      )}
                      style={{ background: p.thumb }}
                    >
                      {selected ? (
                        <span className="absolute inset-0 flex items-center justify-center bg-black/30">
                          <span className="text-[10px] font-bold text-white">
                            ✓
                          </span>
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">或上传自定义背景图</Label>
              <div className="flex items-center gap-3">
                <div className="flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-muted">
                  {draft.background_image_data_url ? (
                    <img
                      src={draft.background_image_data_url}
                      alt="bg preview"
                      className="size-full object-cover"
                    />
                  ) : (
                    <ImageIcon className="size-5 text-muted-foreground" strokeWidth={1.75} />
                  )}
                </div>
                <div className="flex flex-1 flex-wrap items-center gap-2">
                  <input
                    ref={bgFileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleBgPick}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5"
                    onClick={() => bgFileRef.current?.click()}
                    disabled={bgUploading}
                  >
                    {bgUploading ? (
                      <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
                    ) : (
                      <Upload className="size-3.5" strokeWidth={1.75} />
                    )}
                    {draft.background_image_data_url ? '更换' : '上传'}
                  </Button>
                  {draft.background_image_data_url ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 gap-1.5 text-danger"
                      onClick={clearBackground}
                    >
                      <Trash2 className="size-3.5" strokeWidth={1.75} />
                      清除
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>

            {/* 背景图调节(只在有背景图时显示) */}
            {draft.background_image_data_url ? (
              <>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">透明度(图可见度)</Label>
                    <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                      {Math.round(draft.background_opacity * 100)}%
                    </span>
                  </div>
                  <Slider
                    value={[draft.background_opacity]}
                    min={0}
                    max={1}
                    step={0.05}
                    onValueChange={(v) =>
                      setDraft((d) => ({ ...d, background_opacity: v[0] ?? 0.3 }))
                    }
                  />
                  <p className="text-[10.5px] text-muted-foreground">
                    0% = 全黑遮罩(看不见图);100% = 完全可见(无遮罩)
                  </p>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">模糊度</Label>
                    <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                      {draft.background_blur} px
                    </span>
                  </div>
                  <Slider
                    value={[draft.background_blur]}
                    min={0}
                    max={40}
                    step={1}
                    onValueChange={(v) =>
                      setDraft((d) => ({ ...d, background_blur: v[0] ?? 0 }))
                    }
                  />
                  <p className="text-[10.5px] text-muted-foreground">
                    0 = 不模糊;高斯模糊增强后内容可读性
                  </p>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">混合模式</Label>
                  <Select
                    value={draft.background_blend_mode}
                    onValueChange={(v) =>
                      setDraft((d) => ({ ...d, background_blend_mode: v }))
                    }
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="max-h-[260px]">
                      {BLEND_MODE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            ) : (
              <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
                上传背景图后可调节透明度 / 模糊 / 混合模式
              </p>
            )}
          </div>
        </div>
      )}

      {/* 保存 / 重置 — 双列底部 */}
      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border/60 pt-4">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? (
            <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
          ) : (
            <Save className="mr-1.5 size-4" strokeWidth={1.75} />
          )}
          保存外观设置
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleReset}
          disabled={update.isPending}
        >
          <RotateCcw className="mr-1.5 size-4" strokeWidth={1.75} />
          恢复默认
        </Button>
        {dirty ? (
          <p className="ml-auto text-[11px] text-muted-foreground">
            ⚠️ 有未保存改动,点保存才生效
          </p>
        ) : (
          <p className="ml-auto text-[11px] text-muted-foreground">设置生效全站</p>
        )}
      </div>
    </Card>
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
