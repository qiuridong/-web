/**
 * /scripts/:slug — 脚本详情页
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.5(详情页 wireframe)、§ 4、§ 8。
 *
 * 结构:
 *   PageHeader 容纳 hero(icon + 名称 + version + 状态 + 操作组)
 *   ┌─────── Tabs(6 个) ───────┐
 *   │ 概览 / 实例 / 配置 schema / 历史 / 实时日志 / README │
 *   └────────────────────────────┘
 *
 * 数据 hooks:useScript(slug) / useScanScripts / useEnableScript / useDisableScript / useDeleteScript
 *
 * 批次 6C 升级:
 *   - 实例 Tab → <InstancesPanel script={script} onTriggered={(id, runId) => 切到 logs + setRunId}>
 *   - 执行历史 Tab → <RunsPanel filter={{ script_slug }}>
 *   - 实时日志 Tab → <LogViewer runId={selectedRunId}>(配合 select 切换 runId)
 */
import { useMemo, useState, type ReactNode } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowLeft,
  CalendarClock,
  Clock,
  ExternalLink,
  History,
  Info,
  Layers,
  Loader2,
  Pause,
  PlayCircle,
  RefreshCw,
  ScrollText,
  Settings,
  Terminal,
  TriangleAlert,
  User,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import EmptyState from '@/components/common/EmptyState';
import InstancesPanel from '@/components/common/InstancesPanel';
import LogViewer from '@/components/common/LogViewer';
import PageHeader from '@/components/common/PageHeader';
import RunsPanel from '@/components/common/RunsPanel';
import FileEditDialog from './components/FileEditDialog';
import ScriptFileList from './components/ScriptFileList';
import type { ScriptFileItem } from '@/api/hooks/useScriptFiles';

import {
  useDisableScript,
  useEnableScript,
  useScanScripts,
  useScript,
  type ScriptDetail as ScriptDetailModel,
  type ScriptField,
  type ScriptFieldType,
} from '@/api/hooks/scripts';
import { useRuns } from '@/api/hooks/runs';
import { formatDate, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

type TabValue =
  | 'overview'
  | 'instances'
  | 'schema'
  | 'history'
  | 'logs'
  | 'readme';

export function ScriptDetail() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const navigate = useNavigate();
  const location = useLocation();

  const { data: script, isLoading, isError, error, refetch } = useScript(slug);

  const scan = useScanScripts();
  const enable = useEnableScript();
  const disable = useDisableScript();

  // location.state 支持 InstancesPanel onTriggered 跳转 tab + 选中 runId
  const initialState = (location.state ?? {}) as {
    activeTab?: TabValue;
    runId?: number;
  };
  const [activeTab, setActiveTab] = useState<TabValue>(initialState.activeTab ?? 'overview');
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(initialState.runId);

  // === MVP-5:文件编辑 / 查看 Dialog 状态 ===
  const [editingFile, setEditingFile] = useState<{
    file: ScriptFileItem;
    mode: 'edit' | 'view';
  } | null>(null);

  // 实时日志 tab 用:列最近 20 条 run 供切换
  const { data: recentRuns } = useRuns({
    script_slug: slug,
    page_size: 20,
    order: 'desc',
  });
  // 默认选最新的一条
  const fallbackRunId = useMemo(() => {
    if (selectedRunId) return selectedRunId;
    return recentRuns && recentRuns.length > 0 ? recentRuns[0]?.id : undefined;
  }, [selectedRunId, recentRuns]);

  // === loading skeleton ===
  if (isLoading) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
        <DetailSkeleton />
      </div>
    );
  }

  // === error 态 ===
  if (isError || !script) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
        <Button
          variant="ghost"
          size="sm"
          className="mb-4 -ml-2"
          onClick={() => navigate('/scripts')}
        >
          <ArrowLeft className="size-4" strokeWidth={1.75} />
          <span className="ml-1.5">返回列表</span>
        </Button>
        <div className="rounded-xl border-2 border-dashed border-danger/40 bg-card/30">
          <EmptyState
            icon={TriangleAlert}
            title="无法加载脚本详情"
            description={
              (error as Error | undefined)?.message ??
              `slug = ${slug ?? '(无)'};可能已被移除或扫描尚未发现。`
            }
            action={
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => refetch()}>
                  <RefreshCw className="size-4" strokeWidth={1.75} />
                  <span className="ml-1.5">重试</span>
                </Button>
                <Button onClick={() => scan.mutate()} disabled={scan.isPending}>
                  {scan.isPending ? (
                    <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
                  ) : (
                    <RefreshCw className="size-4" strokeWidth={1.75} />
                  )}
                  <span className="ml-1.5">扫描脚本</span>
                </Button>
              </div>
            }
          />
        </div>
      </div>
    );
  }

  // === 主渲染 ===
  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      {/* breadcrumb 用 PageHeader 内置 */}
      <PageHeader
        title={script.name}
        description={script.description ?? '(无描述)'}
        breadcrumb={[
          { label: '脚本', to: '/scripts' },
          { label: script.name },
        ]}
        actions={
          <>
            {script.enabled ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => disable.mutate(script.slug)}
                disabled={disable.isPending}
              >
                {disable.isPending ? (
                  <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <Pause className="size-4" strokeWidth={1.75} />
                )}
                <span className="ml-1.5">禁用</span>
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => enable.mutate(script.slug)}
                disabled={enable.isPending}
              >
                {enable.isPending ? (
                  <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <PlayCircle className="size-4" strokeWidth={1.75} />
                )}
                <span className="ml-1.5">启用</span>
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
            >
              {scan.isPending ? (
                <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <RefreshCw className="size-4" strokeWidth={1.75} />
              )}
              <span className="ml-1.5 hidden sm:inline">扫描更新</span>
            </Button>
          </>
        }
      />

      {/* Hero 行:icon + slug + 版本 + 状态 */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <ScriptInitialLarge slug={script.slug} name={script.name} />
        <code className="rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
          {script.slug}
        </code>
        <Badge variant="outline" className="font-mono">
          v{script.version}
        </Badge>
        {script.enabled ? (
          <Badge
            variant="outline"
            className="border-success/30 bg-success/10 font-normal text-success"
          >
            已启用
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="border-muted-foreground/20 font-normal text-muted-foreground"
          >
            已禁用
          </Badge>
        )}
        {script.author ? (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <User className="size-3" strokeWidth={1.75} />
            {script.author}
          </span>
        ) : null}
        {script.homepage ? (
          <a
            href={script.homepage}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <ExternalLink className="size-3" strokeWidth={1.75} />
            主页
          </a>
        ) : null}
      </div>

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as TabValue)}
        className="w-full"
      >
        <TabsList className="h-10 w-full justify-start gap-0.5 rounded-md border-b border-border bg-transparent p-0">
          <DetailTab value="overview" icon={Info}>
            概览
          </DetailTab>
          <DetailTab value="instances" icon={Layers}>
            实例
            {script.instance_count > 0 ? (
              <Badge
                variant="outline"
                className="ml-1.5 h-5 min-w-[20px] px-1.5 text-[10px] tabular-nums"
              >
                {script.instance_count}
              </Badge>
            ) : null}
          </DetailTab>
          <DetailTab value="schema" icon={Settings}>
            配置 schema
          </DetailTab>
          <DetailTab value="history" icon={History}>
            执行历史
          </DetailTab>
          <DetailTab value="logs" icon={Terminal}>
            实时日志
          </DetailTab>
          <DetailTab value="readme" icon={ScrollText}>
            README
          </DetailTab>
        </TabsList>

        {/* 概览 */}
        <TabsContent value="overview" className="mt-5 space-y-5">
          <OverviewPanel script={script} />
          <ScriptFileList
            slug={script.slug}
            onView={(file) => setEditingFile({ file, mode: 'view' })}
            onEdit={(file) => setEditingFile({ file, mode: 'edit' })}
          />
        </TabsContent>

        {/* 实例 */}
        <TabsContent value="instances" className="mt-5">
          <InstancesPanel
            script={script}
            onTriggered={(_instanceId, runId) => {
              setSelectedRunId(runId);
              setActiveTab('logs');
            }}
          />
        </TabsContent>

        {/* 配置 schema */}
        <TabsContent value="schema" className="mt-5">
          <SchemaPanel fields={script.fields_schema} />
        </TabsContent>

        {/* 执行历史 */}
        <TabsContent value="history" className="mt-5">
          <RunsPanel filter={{ script_slug: script.slug }} />
        </TabsContent>

        {/* 实时日志 */}
        <TabsContent value="logs" className="mt-5">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                选择一条 run 查看实时日志:
              </span>
              <Select
                value={fallbackRunId ? String(fallbackRunId) : ''}
                onValueChange={(v) => setSelectedRunId(v ? Number(v) : undefined)}
              >
                <SelectTrigger className="h-9 w-[280px] text-sm">
                  <SelectValue placeholder="(无可选 run)" />
                </SelectTrigger>
                <SelectContent>
                  {(recentRuns ?? []).map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      <span className="tabular-nums">
                        #{r.id} · {r.status} · {formatDate(r.started_at, 'MM-dd HH:mm:ss')}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Badge variant="outline" className="text-[11px]">
                共 {recentRuns?.length ?? 0} 条最近
              </Badge>
            </div>
            {fallbackRunId ? (
              <LogViewer runId={fallbackRunId} />
            ) : (
              <Card className="border-2 border-dashed border-border bg-card/30">
                <EmptyState
                  icon={Terminal}
                  title="尚无 run 可查看"
                  description='在"实例"Tab 中点击「立即运行」生成一条 run,即可在此查看日志'
                />
              </Card>
            )}
          </div>
        </TabsContent>

        {/* README */}
        <TabsContent value="readme" className="mt-5">
          <ReadmePanel md={script.readme_md ?? ''} />
        </TabsContent>
      </Tabs>

      {/* MVP-5:文件编辑 / 查看 Dialog */}
      {editingFile ? (
        <FileEditDialog
          open={!!editingFile}
          onOpenChange={(open) => {
            if (!open) setEditingFile(null);
          }}
          slug={script.slug}
          path={editingFile.file.path}
          meta={editingFile.file}
          mode={editingFile.mode}
        />
      ) : null}
    </div>
  );
}

// ============ 子组件 ============

function DetailTab({
  value,
  icon: Icon,
  children,
}: {
  value: TabValue;
  icon: typeof Info;
  children: ReactNode;
}) {
  return (
    <TabsTrigger
      value={value}
      className={cn(
        'group relative h-10 gap-1.5 rounded-none border-b-2 border-transparent bg-transparent px-3 text-sm font-medium text-muted-foreground transition-colors',
        'data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none',
        'hover:text-foreground',
      )}
    >
      <Icon className="size-4" strokeWidth={1.75} />
      {children}
    </TabsTrigger>
  );
}

function OverviewPanel({ script }: { script: ScriptDetailModel }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="col-span-2 p-6">
        <h3 className="mb-4 text-sm font-semibold text-foreground">基本信息</h3>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
          <Field label="slug">
            <code className="font-mono text-xs text-muted-foreground">
              {script.slug}
            </code>
          </Field>
          <Field label="版本">
            <Badge variant="outline" className="font-mono">
              v{script.version}
            </Badge>
          </Field>
          <Field label="作者">
            {script.author ?? <span className="text-muted-foreground/60">—</span>}
          </Field>
          <Field label="主页">
            {script.homepage ? (
              <a
                href={script.homepage}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                {script.homepage}
                <ExternalLink className="size-3" strokeWidth={1.75} />
              </a>
            ) : (
              <span className="text-muted-foreground/60">—</span>
            )}
          </Field>
          <Field label="default cron">
            {script.default_cron ? (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                {script.default_cron}
              </code>
            ) : (
              <span className="text-muted-foreground/60">无默认</span>
            )}
          </Field>
          <Field label="default timeout">
            {script.default_timeout_sec ? (
              <span className="tabular-nums text-foreground">
                {script.default_timeout_sec} 秒
              </span>
            ) : (
              <span className="text-muted-foreground/60">—</span>
            )}
          </Field>
          <Field label="requirements.txt">
            {script.requirements_present ? (
              <Badge
                variant="outline"
                className="border-info/30 bg-info/10 font-normal text-info"
              >
                存在
              </Badge>
            ) : (
              <span className="text-muted-foreground/60">无</span>
            )}
          </Field>
          <Field label="字段数">
            <span className="tabular-nums">{script.fields_schema.length}</span>
          </Field>
          <Field label="实例数">
            <span className="tabular-nums">{script.instance_count}</span>
          </Field>
          <Field label="last_scanned_at">
            <span
              className="text-muted-foreground"
              title={formatDate(script.last_scanned_at)}
            >
              {formatRelative(script.last_scanned_at)}
            </span>
          </Field>
        </dl>
      </Card>

      <Card className="p-6">
        <h3 className="mb-4 text-sm font-semibold text-foreground">运行时</h3>
        {script.runtime ? (
          <dl className="space-y-3 text-sm">
            <Field label="Python">
              <code className="font-mono text-xs text-muted-foreground">
                {script.runtime.python_version ?? '默认'}
              </code>
            </Field>
            <Field label="独立子进程">
              {script.runtime.isolated !== false ? (
                <Badge
                  variant="outline"
                  className="border-success/30 bg-success/10 font-normal text-success"
                >
                  是
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="border-warning/30 bg-warning/10 font-normal text-warning"
                >
                  否(同进程)
                </Badge>
              )}
            </Field>
            <Field label="env 透传">
              {script.runtime.env_passthrough &&
              script.runtime.env_passthrough.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {script.runtime.env_passthrough.map((v) => (
                    <code
                      key={v}
                      className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {v}
                    </code>
                  ))}
                </div>
              ) : (
                <span className="text-muted-foreground/60">—</span>
              )}
            </Field>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">采用默认运行时配置</p>
        )}

        <div className="mt-6 space-y-2 border-t border-border pt-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <CalendarClock className="size-3" strokeWidth={1.75} />
            <span>下次执行:{formatRelative(script.next_run_at)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="size-3" strokeWidth={1.75} />
            <span>上次执行:{formatRelative(script.last_run_at)}</span>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <dt className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
        {label}
      </dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}

function SchemaPanel({ fields }: { fields: ScriptField[] }) {
  if (fields.length === 0) {
    return (
      <Card className="border-2 border-dashed border-border bg-card/30">
        <EmptyState
          icon={Settings}
          title="未声明任何字段"
          description="manifest.yaml 的 fields[] 为空,创建实例时无需配置"
        />
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        以下为 manifest.yaml 中声明的实例配置字段(只读预览)。创建实例时会按此渲染表单。
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {fields.map((f) => (
          <FieldPreview key={f.key} field={f} />
        ))}
      </div>
    </div>
  );
}

function FieldPreview({ field }: { field: ScriptField }) {
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-foreground">
            {field.label}
            {field.required ? (
              <span className="ml-1 text-danger" aria-label="required">
                *
              </span>
            ) : null}
          </h4>
          <code className="mt-0.5 inline-block font-mono text-[11px] text-muted-foreground">
            {field.key}
          </code>
        </div>
        <FieldTypeBadge type={field.type} />
      </div>
      {field.description ? (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {field.description}
        </p>
      ) : null}
      <FieldExtraAttrs field={field} />
    </Card>
  );
}

function FieldTypeBadge({ type }: { type: ScriptFieldType }) {
  // 不同 type 给不同色相,沿用 chart-N
  const colorMap: Record<ScriptFieldType, string> = {
    string: 'chart-1',
    secret: 'chart-5', // 红 = 敏感
    integer: 'chart-2',
    boolean: 'chart-3',
    select: 'chart-4',
    multiselect: 'chart-4',
    multiline: 'chart-1',
    cron: 'chart-2',
    url: 'chart-2',
    json: 'chart-3',
  };
  const color = colorMap[type];
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-medium"
      style={{
        borderColor: `color-mix(in oklch, var(--${color}) 30%, transparent)`,
        background: `color-mix(in oklch, var(--${color}) 12%, transparent)`,
        color: `var(--${color})`,
      }}
    >
      {type}
    </span>
  );
}

function FieldExtraAttrs({ field }: { field: ScriptField }) {
  const items: { label: string; value: string }[] = [];

  // 默认值
  if (field.default !== undefined && field.default !== null) {
    items.push({
      label: 'default',
      value:
        typeof field.default === 'object'
          ? JSON.stringify(field.default)
          : String(field.default),
    });
  }
  if (field.placeholder) {
    items.push({ label: 'placeholder', value: field.placeholder });
  }
  if (typeof field.min === 'number') items.push({ label: 'min', value: String(field.min) });
  if (typeof field.max === 'number') items.push({ label: 'max', value: String(field.max) });
  if (typeof field.step === 'number') items.push({ label: 'step', value: String(field.step) });
  if (typeof field.min_length === 'number') {
    items.push({ label: 'min_len', value: String(field.min_length) });
  }
  if (typeof field.max_length === 'number') {
    items.push({ label: 'max_len', value: String(field.max_length) });
  }
  if (field.pattern) items.push({ label: 'pattern', value: field.pattern });
  if (typeof field.rows === 'number') items.push({ label: 'rows', value: String(field.rows) });
  if (typeof field.min_items === 'number') {
    items.push({ label: 'min_items', value: String(field.min_items) });
  }
  if (typeof field.max_items === 'number') {
    items.push({ label: 'max_items', value: String(field.max_items) });
  }
  if (field.schemes && field.schemes.length > 0) {
    items.push({ label: 'schemes', value: field.schemes.join(', ') });
  }

  const showOptions =
    (field.type === 'select' || field.type === 'multiselect') &&
    field.options &&
    field.options.length > 0;

  if (items.length === 0 && !showOptions) return null;

  return (
    <div className="mt-3 space-y-2 border-t border-border/50 pt-3">
      {items.length > 0 ? (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          {items.map((it) => (
            <div key={it.label} className="flex min-w-0 gap-1">
              <dt className="shrink-0 text-muted-foreground/70">{it.label}:</dt>
              <dd className="truncate font-mono text-muted-foreground">
                {it.value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {showOptions ? (
        <div>
          <div className="mb-1 text-[11px] text-muted-foreground/70">
            options:
          </div>
          <div className="flex flex-wrap gap-1">
            {field.options!.map((o) => (
              <code
                key={o.value}
                className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                title={o.description ?? o.label}
              >
                {o.label}
              </code>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ReadmePanel({ md }: { md: string }) {
  if (!md || md.trim() === '') {
    return (
      <Card className="border-2 border-dashed border-border bg-card/30">
        <EmptyState
          icon={ScrollText}
          title="脚本未提供 README.md"
          description="在脚本目录添加 README.md,这里会自动渲染"
        />
      </Card>
    );
  }
  return (
    <Card className="p-6 md:p-8">
      <article className="prose prose-zinc max-w-3xl text-sm dark:prose-invert">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ ...props }) => (
              <a {...props} target="_blank" rel="noopener noreferrer" />
            ),
          }}
        >
          {md}
        </ReactMarkdown>
      </article>
    </Card>
  );
}

function ScriptInitialLarge({ slug, name }: { slug: string; name: string }) {
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) | 0;
  const variant = (Math.abs(h) % 5) + 1;
  const first = name.trim()[0] ?? slug[0] ?? '·';
  const isAscii = /[A-Za-z]/.test(first);
  return (
    <div
      className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-border/50 text-lg font-semibold"
      style={{
        background: `color-mix(in oklch, var(--chart-${variant}) 14%, transparent)`,
        color: `var(--chart-${variant})`,
      }}
      aria-hidden
    >
      {isAscii ? first.toUpperCase() : first}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-8 w-16" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="size-12 rounded-xl" />
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-16" />
      </div>
      <Skeleton className="h-10 w-full" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="col-span-2 h-[300px]" />
        <Skeleton className="h-[300px]" />
      </div>
    </div>
  );
}

export default ScriptDetail;
