/**
 * /notifications — 通知中心
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.9。
 *
 * 两个 Tabs:
 *   - 渠道:卡片网格(name / type 图标 / enabled / 测试发送)+ 新建渠道(Sheet 表单)
 *   - 规则:DataTable + 新建规则(Sheet 表单)
 */
import { useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import {
  Bell,
  BookOpen,
  CheckCircle2,
  CircleX,
  Globe,
  Loader2,
  Mail,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Plus,
  Send,
  Smartphone,
  Sparkles,
  Trash2,
  TriangleAlert,
  Webhook,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

import DataTable from '@/components/common/DataTable';
import EmptyState from '@/components/common/EmptyState';
import PageHeader from '@/components/common/PageHeader';
import SecretInput from '@/components/common/SecretInput';

import {
  useCreateChannel,
  useCreateRule,
  useDeleteChannel,
  useDeleteRule,
  useNotificationChannels,
  useNotificationRules,
  useTestChannel,
  useUpdateChannel,
  useUpdateRule,
  type ChannelCreatePayload,
  type ChannelUpdatePayload,
  type NotificationChannel,
  type NotificationEvent,
  type NotificationRule,
  type NotificationScope,
  type RuleCreatePayload,
  type RuleUpdatePayload,
} from '@/api/hooks/notifications';
import { useScripts } from '@/api/hooks/scripts';
import { useInstances } from '@/api/hooks/instances';
import { formatRelative } from '@/lib/format';
import {
  CHANNEL_PRESETS,
  TEMPLATE_FIELD_GROUPS,
  TEMPLATE_FORMAT_NOTE,
  TEMPLATE_PRESETS,
} from '@/lib/notification-presets';
import { cn } from '@/lib/utils';

type Tab = 'channels' | 'rules';

export function NotificationHub() {
  const [tab, setTab] = useState<Tab>('channels');

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader
        title="通知"
        description="管理 apprise 渠道与触发规则,实现签到结果实时推送"
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="w-full">
        <TabsList className="h-10 w-full justify-start gap-0.5 rounded-md border-b border-border bg-transparent p-0">
          <NotifyTab value="channels">渠道</NotifyTab>
          <NotifyTab value="rules">规则</NotifyTab>
        </TabsList>

        <TabsContent value="channels" className="mt-5">
          <ChannelsPanel />
        </TabsContent>

        <TabsContent value="rules" className="mt-5">
          <RulesPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function NotifyTab({ value, children }: { value: Tab; children: ReactNode }) {
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

/* ============ 渠道 ============ */

function channelIcon(url: string | null | undefined) {
  const scheme = (url ?? '').split(':')[0]?.toLowerCase() ?? '';
  if (scheme.startsWith('tgram') || scheme.startsWith('telegram')) return MessageCircle;
  if (scheme === 'mailto' || scheme.startsWith('smtp')) return Mail;
  if (scheme.startsWith('ding') || scheme.startsWith('lark') || scheme.startsWith('wxteams')) return MessageCircle;
  if (scheme.startsWith('http') || scheme.startsWith('json') || scheme.startsWith('xml')) return Webhook;
  if (scheme.startsWith('sms') || scheme.startsWith('twilio')) return Smartphone;
  if (scheme.startsWith('bark')) return Bell;
  if (scheme === '' || scheme === 'null') return Globe;
  return Globe;
}

function ChannelsPanel() {
  const { data: channels, isLoading } = useNotificationChannels();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | undefined>(undefined);
  const [deleteTarget, setDeleteTarget] = useState<NotificationChannel | null>(null);
  const remove = useDeleteChannel();
  const test = useTestChannel();

  function openCreate() {
    setEditing(undefined);
    setOpen(true);
  }

  function openEdit(c: NotificationChannel) {
    setEditing(c);
    setOpen(true);
  }

  function handleClose(o: boolean) {
    setOpen(o);
    if (!o) setEditing(undefined);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-muted-foreground">
          {channels && channels.length > 0
            ? `共 ${channels.length} 个渠道`
            : '尚未配置任何渠道'}
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="size-4" strokeWidth={1.75} />
          <span className="ml-1.5">新建渠道</span>
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">加载中…</p>
      ) : !channels || channels.length === 0 ? (
        <Card className="border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Bell}
            title="还没有通知渠道"
            description="配置 apprise URL(如 Telegram / Email / 飞书 / 钉钉等)即可接收签到结果推送"
            action={
              <Button onClick={openCreate}>
                <Sparkles className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">立即创建</span>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map((c) => (
            <ChannelCard
              key={c.id}
              channel={c}
              onTest={() => test.mutate({ id: c.id })}
              testing={test.isPending && test.variables?.id === c.id}
              onEdit={() => openEdit(c)}
              onDelete={() => setDeleteTarget(c)}
            />
          ))}
        </div>
      )}

      <ChannelSheet
        open={open}
        onOpenChange={handleClose}
        channel={editing}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <TriangleAlert className="size-5 text-danger" strokeWidth={1.75} />
              确认删除渠道「{deleteTarget?.name}」?
            </AlertDialogTitle>
            <AlertDialogDescription>
              <strong className="text-foreground">将级联删除该渠道下的所有通知规则</strong>;不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault();
                if (!deleteTarget) return;
                remove.mutate(deleteTarget.id, {
                  onSuccess: () => setDeleteTarget(null),
                });
              }}
            >
              {remove.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Trash2 className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface ChannelCardProps {
  channel: NotificationChannel;
  testing: boolean;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function ChannelCard({ channel, testing, onTest, onEdit, onDelete }: ChannelCardProps) {
  const Icon = channelIcon(channel.apprise_url);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <h4 className="truncate text-sm font-semibold text-foreground">{channel.name}</h4>
            <p className="truncate font-mono text-[11px] text-muted-foreground">
              {channel.apprise_url ?? '—'}
            </p>
          </div>
        </div>
        {channel.enabled ? (
          <Badge variant="outline" className="border-success/30 bg-success/10 text-success">
            启用
          </Badge>
        ) : (
          <Badge variant="outline" className="text-muted-foreground">
            禁用
          </Badge>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          {channel.last_test_at ? (
            <>
              上次测试:{formatRelative(channel.last_test_at)}
              {channel.last_test_ok ? (
                <CheckCircle2 className="ml-1 inline size-3 text-success" strokeWidth={1.75} />
              ) : channel.last_test_ok === false ? (
                <CircleX className="ml-1 inline size-3 text-danger" strokeWidth={1.75} />
              ) : null}
            </>
          ) : (
            '尚未测试'
          )}
        </span>
        <span className="font-mono">{channel.type}</span>
      </div>

      <div className="flex items-center gap-1.5 border-t border-border/60 pt-3">
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5"
          onClick={onTest}
          disabled={testing}
        >
          {testing ? (
            <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Send className="size-3.5" strokeWidth={1.75} />
          )}
          测试发送
        </Button>
        <Button variant="outline" size="sm" className="h-8 gap-1.5" onClick={onEdit}>
          <Pencil className="size-3.5" strokeWidth={1.75} />
          编辑
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="ml-auto size-8 p-0">
              <MoreHorizontal className="size-4" strokeWidth={1.75} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="text-xs">操作</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onDelete} className="text-danger focus:text-danger">
              <Trash2 className="mr-2 size-3.5" strokeWidth={1.75} />
              删除渠道
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}

interface ChannelSheetProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  channel?: NotificationChannel;
}

function ChannelSheet({ open, onOpenChange, channel }: ChannelSheetProps) {
  const isEdit = !!channel;
  const create = useCreateChannel();
  const update = useUpdateChannel();
  const submitting = create.isPending || update.isPending;

  const [name, setName] = useState('');
  const [apprise_url, setUrl] = useState('');
  const [urlTouched, setUrlTouched] = useState(false);
  const [description, setDescription] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [presetId, setPresetId] = useState<string>('');

  const currentPreset = useMemo(
    () => CHANNEL_PRESETS.find((p) => p.id === presetId),
    [presetId],
  );

  // 在打开时初始化
  useMemo(() => {
    if (!open) return;
    setName(channel?.name ?? '');
    setUrl('');
    setUrlTouched(false);
    setDescription(channel?.description ?? '');
    setEnabled(channel?.enabled ?? true);
    setPresetId('');
  }, [open, channel]);

  function applyChannelPreset(id: string) {
    setPresetId(id);
    const preset = CHANNEL_PRESETS.find((p) => p.id === id);
    if (!preset) return;
    setUrl(preset.urlTemplate);
    setUrlTouched(true);
    if (preset.urlTemplate) {
      toast.info('已填入示例 URL,请把占位符(如 BOT_TOKEN、CHAT_ID)换成你的实际值', {
        duration: 5000,
      });
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('请填写名称');
      return;
    }
    if (isEdit && channel) {
      const payload: ChannelUpdatePayload = {
        name,
        description: description || undefined,
        enabled,
      };
      if (urlTouched && apprise_url.trim()) {
        payload.apprise_url = apprise_url.trim();
      }
      await update.mutateAsync({ id: channel.id, payload });
    } else {
      if (!apprise_url.trim()) {
        toast.error('请填写 apprise URL');
        return;
      }
      const payload: ChannelCreatePayload = {
        name,
        apprise_url: apprise_url.trim(),
        description: description || undefined,
        enabled,
      };
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-md"
      >
        <SheetHeader className="shrink-0 border-b border-border px-6 pb-4 pt-6">
          <SheetTitle>{isEdit ? '编辑渠道' : '新建渠道'}</SheetTitle>
          <SheetDescription>
            v1 仅支持 apprise(覆盖 80+ 渠道,Telegram/邮件/钉钉/飞书 等)
          </SheetDescription>
        </SheetHeader>

        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5 [scrollbar-gutter:stable]">
          <div className="space-y-1.5">
            <Label htmlFor="ch-name">
              名称<span className="ml-0.5 text-danger">*</span>
            </Label>
            <Input
              id="ch-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如 运维 TG / 个人邮箱"
              className="h-10"
            />
          </div>

          <div className="space-y-1.5">
            <Label>渠道类型预设</Label>
            <Select value={presetId} onValueChange={applyChannelPreset}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="选一个常用渠道,自动填入 URL 模板" />
              </SelectTrigger>
              <SelectContent className="max-h-[280px]">
                {CHANNEL_PRESETS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {currentPreset && currentPreset.id !== 'custom' ? (
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {currentPreset.helper}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                选中后会把 URL 模板填到下方,你只需替换占位符;不熟悉可看{' '}
                <a
                  href="https://github.com/caronc/apprise/wiki"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-foreground"
                >
                  apprise wiki
                </a>
                。
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ch-url">
              Apprise URL{!isEdit && <span className="ml-0.5 text-danger">*</span>}
            </Label>
            <SecretInput
              id="ch-url"
              value={apprise_url}
              onChange={(v) => setUrl(v)}
              onTouched={() => setUrlTouched(true)}
              isSet={isEdit && !!channel?.apprise_url}
              mode={isEdit ? 'edit' : 'create'}
              placeholder="tgram://BOTTOKEN/CHATID"
            />
            <p className="text-[11px] text-muted-foreground">
              默认以密文显示,点 <span className="font-mono">👁</span> 切换明文以编辑占位符。
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ch-desc">备注</Label>
            <Textarea
              id="ch-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="给自己看的说明,可选"
            />
          </div>

          <div className="flex items-center gap-3">
            <Switch id="ch-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="ch-enabled" className="text-sm font-normal">
              启用该渠道
            </Label>
          </div>

          </div>

          <SheetFooter className="flex shrink-0 flex-row-reverse gap-2 border-t border-border bg-background px-6 py-4">
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : null}
              {isEdit ? '保存修改' : '创建'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              取消
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}

/* ============ 规则 ============ */

function RulesPanel() {
  const { data: rules, isLoading } = useNotificationRules();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationRule | undefined>(undefined);
  const [deleteTarget, setDeleteTarget] = useState<NotificationRule | null>(null);
  const remove = useDeleteRule();

  function openCreate() {
    setEditing(undefined);
    setOpen(true);
  }

  function openEdit(r: NotificationRule) {
    setEditing(r);
    setOpen(true);
  }

  function handleClose(o: boolean) {
    setOpen(o);
    if (!o) setEditing(undefined);
  }

  const columns = useMemo<ColumnDef<NotificationRule>[]>(
    () => [
      {
        accessorKey: 'name',
        header: '名称',
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{row.original.name}</div>
            <div className="text-[11px] text-muted-foreground">
              {row.original.enabled ? '启用' : '禁用'}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'scope',
        header: '作用域',
        cell: ({ row }) => {
          const r = row.original;
          const labelMap: Record<NotificationScope, string> = {
            global: '全局',
            script: '脚本',
            instance: '实例',
          };
          return (
            <div className="text-xs">
              <Badge variant="outline" className="mr-1">
                {labelMap[r.scope] ?? r.scope}
              </Badge>
              {r.script?.name ? (
                <span className="font-mono text-[11px] text-muted-foreground">
                  {r.script.name}
                </span>
              ) : null}
              {r.instance?.name ? (
                <span className="ml-1 font-mono text-[11px] text-muted-foreground">
                  / {r.instance.name}
                </span>
              ) : null}
            </div>
          );
        },
      },
      {
        accessorKey: 'event',
        header: '事件',
        cell: ({ row }) => (
          <Badge variant="outline" className="font-mono">
            {row.original.event}
          </Badge>
        ),
      },
      {
        accessorKey: 'channel_id',
        header: '渠道',
        cell: ({ row }) => (
          <span className="text-xs">
            {row.original.channel?.name ?? `#${row.original.channel_id}`}
          </span>
        ),
      },
      {
        accessorKey: 'min_interval_sec',
        header: '节流',
        cell: ({ getValue }) => {
          const v = (getValue() as number) ?? 0;
          return (
            <span className="text-xs tabular-nums text-muted-foreground">
              {v > 0 ? `${v} 秒` : '不限'}
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              onClick={(e) => {
                e.stopPropagation();
                openEdit(row.original);
              }}
              aria-label="编辑"
            >
              <Pencil className="size-3.5" strokeWidth={1.75} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0 text-danger hover:text-danger"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row.original);
              }}
              aria-label="删除"
            >
              <Trash2 className="size-3.5" strokeWidth={1.75} />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-muted-foreground">
          {rules && rules.length > 0
            ? `共 ${rules.length} 条规则`
            : '尚未配置任何规则'}
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="size-4" strokeWidth={1.75} />
          <span className="ml-1.5">新建规则</span>
        </Button>
      </div>

      <DataTable<NotificationRule, unknown>
        columns={columns}
        data={rules ?? []}
        loading={isLoading}
        onRowClick={(r) => openEdit(r)}
        empty={
          <EmptyState
            icon={Bell}
            title="尚未配置规则"
            description='规则把"事件 → 渠道"绑定起来,如"所有脚本失败 → 运维 TG"'
            action={
              <Button onClick={openCreate}>
                <Sparkles className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">新建规则</span>
              </Button>
            }
          />
        }
        hideColumnVisibility
      />

      <RuleSheet open={open} onOpenChange={handleClose} rule={editing} />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <TriangleAlert className="size-5 text-danger" strokeWidth={1.75} />
              确认删除规则「{deleteTarget?.name}」?
            </AlertDialogTitle>
            <AlertDialogDescription>规则将立即停用,不可恢复。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault();
                if (!deleteTarget) return;
                remove.mutate(deleteTarget.id, {
                  onSuccess: () => setDeleteTarget(null),
                });
              }}
            >
              {remove.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Trash2 className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface RuleSheetProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  rule?: NotificationRule;
}

function RuleSheet({ open, onOpenChange, rule }: RuleSheetProps) {
  const isEdit = !!rule;
  const create = useCreateRule();
  const update = useUpdateRule();
  const submitting = create.isPending || update.isPending;

  const { data: channels } = useNotificationChannels();
  const { data: scripts } = useScripts();

  const [name, setName] = useState('');
  const [scope, setScope] = useState<NotificationScope>('global');
  const [scriptId, setScriptId] = useState<number | undefined>(undefined);
  const [instanceId, setInstanceId] = useState<number | undefined>(undefined);
  const [event, setEvent] = useState<NotificationEvent>('failure');
  const [channelId, setChannelId] = useState<number | undefined>(undefined);
  const [template, setTemplate] = useState('');
  const [minInterval, setMinInterval] = useState('0');
  const [enabled, setEnabled] = useState(true);
  const [templatePresetId, setTemplatePresetId] = useState<string>('');
  const [showFields, setShowFields] = useState(false);
  const templateRef = useRef<HTMLTextAreaElement | null>(null);

  const currentTemplatePreset = useMemo(
    () => TEMPLATE_PRESETS.find((p) => p.id === templatePresetId),
    [templatePresetId],
  );

  // 当 scope=instance 时按 script_id 拉实例
  const scriptSlug = useMemo(() => {
    return scripts?.find((s) => s.id === scriptId)?.slug;
  }, [scripts, scriptId]);
  const { data: instances } = useInstances(
    { script_slug: scriptSlug },
    scope === 'instance' && !!scriptSlug,
  );

  useMemo(() => {
    if (!open) return;
    setName(rule?.name ?? '');
    setScope(rule?.scope ?? 'global');
    setScriptId(rule?.script_id ?? undefined);
    setInstanceId(rule?.instance_id ?? undefined);
    setEvent(rule?.event ?? 'failure');
    setChannelId(rule?.channel_id ?? undefined);
    setTemplate(rule?.template ?? '');
    setMinInterval(String(rule?.min_interval_sec ?? 0));
    setEnabled(rule?.enabled ?? true);
    setTemplatePresetId('');
    setShowFields(false);
  }, [open, rule]);

  function applyTemplatePreset(id: string) {
    setTemplatePresetId(id);
    const preset = TEMPLATE_PRESETS.find((p) => p.id === id);
    if (!preset) return;
    if (template && template.trim() && template !== preset.content) {
      // 用户已经写过内容,提示一下再覆盖(直接覆盖,toast 告知)
      toast.info('已用预设模板覆盖你的输入', { duration: 3000 });
    }
    setTemplate(preset.content);
  }

  function insertField(snippet: string) {
    const el = templateRef.current;
    if (!el) {
      setTemplate((t) => (t ? `${t}${snippet}` : snippet));
      return;
    }
    const start = el.selectionStart ?? template.length;
    const end = el.selectionEnd ?? template.length;
    const next = template.slice(0, start) + snippet + template.slice(end);
    setTemplate(next);
    // 等下一帧把光标定位到插入末尾
    requestAnimationFrame(() => {
      el.focus();
      const caret = start + snippet.length;
      el.setSelectionRange(caret, caret);
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('请填写规则名');
      return;
    }
    if (!channelId) {
      toast.error('请选择渠道');
      return;
    }
    if ((scope === 'script' || scope === 'instance') && !scriptId) {
      toast.error('请选择脚本');
      return;
    }
    if (scope === 'instance' && !instanceId) {
      toast.error('请选择实例');
      return;
    }

    const intervalNum = Number(minInterval);
    if (isEdit && rule) {
      const payload: RuleUpdatePayload = {
        name,
        scope,
        script_id: scope === 'global' ? null : scriptId,
        instance_id: scope === 'instance' ? instanceId : null,
        event,
        channel_id: channelId,
        template: template || null,
        min_interval_sec: Number.isFinite(intervalNum) ? intervalNum : 0,
        enabled,
      };
      await update.mutateAsync({ id: rule.id, payload });
    } else {
      const payload: RuleCreatePayload = {
        name,
        scope,
        script_id: scope === 'global' ? undefined : scriptId,
        instance_id: scope === 'instance' ? instanceId : undefined,
        event,
        channel_id: channelId,
        template: template || undefined,
        min_interval_sec: Number.isFinite(intervalNum) ? intervalNum : 0,
        enabled,
      };
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-md"
      >
        <SheetHeader className="shrink-0 border-b border-border px-6 pb-4 pt-6">
          <SheetTitle>{isEdit ? '编辑规则' : '新建规则'}</SheetTitle>
          <SheetDescription>
            匹配优先级:实例 &gt; 脚本 &gt; 全局,同一渠道只触发最具体的一条
          </SheetDescription>
        </SheetHeader>

        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5 [scrollbar-gutter:stable]">
          <div className="space-y-1.5">
            <Label htmlFor="r-name">
              规则名<span className="ml-0.5 text-danger">*</span>
            </Label>
            <Input
              id="r-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如 失败时通知运维"
              className="h-10"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>作用域</Label>
              <Select
                value={scope}
                onValueChange={(v) => setScope(v as NotificationScope)}
                disabled={event === 'node_offline'}
              >
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[280px]">
                  <SelectItem value="global">全局</SelectItem>
                  <SelectItem value="script">脚本</SelectItem>
                  <SelectItem value="instance">实例</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>事件</Label>
              <Select
                value={event}
                onValueChange={(v) => {
                  const ev = v as NotificationEvent;
                  setEvent(ev);
                  // 节点事件固定全局(后端只匹配 scope=global 的 node 规则)
                  if (ev === 'node_offline') {
                    setScope('global');
                    setScriptId(undefined);
                    setInstanceId(undefined);
                  }
                }}
              >
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[280px]">
                  <SelectItem value="any">任意(运行)</SelectItem>
                  <SelectItem value="success">成功</SelectItem>
                  <SelectItem value="failure">失败</SelectItem>
                  <SelectItem value="error">错误</SelectItem>
                  <SelectItem value="timeout">超时</SelectItem>
                  <SelectItem value="node_offline">🔌 节点掉线</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {scope === 'script' || scope === 'instance' ? (
            <div className="space-y-1.5">
              <Label>脚本</Label>
              <Select
                value={scriptId ? String(scriptId) : ''}
                onValueChange={(v) => {
                  setScriptId(v ? Number(v) : undefined);
                  setInstanceId(undefined);
                }}
              >
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="选择脚本" />
                </SelectTrigger>
                <SelectContent className="max-h-[280px]">
                  {(scripts ?? []).map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {scope === 'instance' ? (
            <div className="space-y-1.5">
              <Label>实例</Label>
              <Select
                value={instanceId ? String(instanceId) : ''}
                onValueChange={(v) => setInstanceId(v ? Number(v) : undefined)}
                disabled={!scriptId || !instances || instances.length === 0}
              >
                <SelectTrigger className="h-10">
                  <SelectValue
                    placeholder={
                      !scriptId
                        ? '请先选脚本'
                        : !instances?.length
                          ? '该脚本无实例'
                          : '选择实例'
                    }
                  />
                </SelectTrigger>
                <SelectContent className="max-h-[280px]">
                  {(instances ?? []).map((i) => (
                    <SelectItem key={i.id} value={String(i.id)}>
                      {i.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label>
              渠道<span className="ml-0.5 text-danger">*</span>
            </Label>
            <Select
              value={channelId ? String(channelId) : ''}
              onValueChange={(v) => setChannelId(v ? Number(v) : undefined)}
            >
              <SelectTrigger className="h-10">
                <SelectValue placeholder="选择推送渠道" />
              </SelectTrigger>
              <SelectContent className="max-h-[280px]">
                {(channels ?? []).map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name} · {c.type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="r-interval">节流间隔(秒,0 = 不限)</Label>
            <Input
              id="r-interval"
              type="number"
              min={0}
              value={minInterval}
              onChange={(e) => setMinInterval(e.target.value)}
              className="h-10 tabular-nums"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="r-tpl">自定义模板(可选,Jinja2)</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                onClick={() => setShowFields((s) => !s)}
                aria-pressed={showFields}
              >
                <BookOpen className="size-3.5" strokeWidth={1.75} />
                字段速查
              </Button>
            </div>
            <Select value={templatePresetId} onValueChange={applyTemplatePreset}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="选预设模板(可选,选中后会覆盖下方内容)" />
              </SelectTrigger>
              <SelectContent className="max-h-[280px]">
                {TEMPLATE_PRESETS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {currentTemplatePreset ? (
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {currentTemplatePreset.description}
              </p>
            ) : null}
            <Textarea
              ref={templateRef}
              id="r-tpl"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={8}
              placeholder="留空使用默认模板;或从上方下拉选预设,再按需调整"
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground">{TEMPLATE_FORMAT_NOTE}</p>

            {showFields ? (
              <Card className="mt-2 space-y-2.5 bg-muted/40 p-3">
                <p className="text-[11px] text-muted-foreground">
                  点击下方任意字段即可插入到模板光标位置。
                </p>
                {TEMPLATE_FIELD_GROUPS.map((group) => (
                  <div key={group.label} className="space-y-1">
                    <div className="text-[11px] font-medium text-foreground">
                      {group.label}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {group.fields.map((f) => (
                        <button
                          type="button"
                          key={f.name}
                          onClick={() => insertField(f.name)}
                          title={f.note ?? f.name}
                          className="rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10.5px] text-foreground hover:bg-accent hover:text-accent-foreground"
                        >
                          {f.name}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            <Switch id="r-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="r-enabled" className="text-sm font-normal">
              启用该规则
            </Label>
          </div>

          </div>

          <SheetFooter className="flex shrink-0 flex-row-reverse gap-2 border-t border-border bg-background px-6 py-4">
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : null}
              {isEdit ? '保存修改' : '创建'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              取消
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}

export default NotificationHub;
