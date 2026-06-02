/**
 * /scripts/marketplace — 脚本市场(脚本货架对接 · M3)
 *
 * 直读「脚本货架」(Script Hub)的公开列表 `GET ${VITE_HUB_URL}/api/scripts`,
 * 卡片网格展示;点「安装」→ 调管家后端 `POST /api/v1/scripts/upload-from-url`
 * (zip_url = ${VITE_HUB_URL}/api/scripts/{slug}/bundle.zip),后端服务端下载入库。
 *
 * 跨域:浏览器直接 GET 货架(货架需 CORS 放行管家 origin);安装是管家后端→货架的
 * 服务端下载(无 CORS 问题)。VITE_HUB_URL 默认 https://hub.aijiaxia.cc。
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Download,
  ExternalLink,
  FileCode2,
  Loader2,
  PackageOpen,
  RefreshCw,
  Search,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import PageHeader from '@/components/common/PageHeader';
import EmptyState from '@/components/common/EmptyState';
import { useUploadScriptFromUrl } from '@/api/hooks/useUploadScriptFromUrl';
import type { UploadError } from '@/api/hooks/useScriptUpload';
import { useDebounce } from '@/hooks/useDebounce';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';

// ====================== 货架 API 契约(见 进度/协作-脚本货架对接.md §3) ======================

interface HubScriptItem {
  slug: string;
  name: string;
  description: string | null;
  version: string;
  author: string | null;
  homepage: string | null;
  tags: string[];
  field_count: number;
  file_count: number;
  size_bytes: number;
  download_count: number;
  has_icon: boolean;
  updated_at: string | null;
}

/** 货架基地址,默认生产货架;末尾斜杠归一化。 */
const HUB_URL: string = (
  import.meta.env.VITE_HUB_URL || 'https://hub.aijiaxia.cc'
).replace(/\/+$/, '');

async function fetchHubScripts(signal?: AbortSignal): Promise<HubScriptItem[]> {
  const resp = await fetch(`${HUB_URL}/api/scripts`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!resp.ok) {
    throw new Error(`货架返回 HTTP ${resp.status}`);
  }
  const data = (await resp.json()) as unknown;
  if (Array.isArray(data)) return data as HubScriptItem[];
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown[] }).items)) {
    return (data as { items: HubScriptItem[] }).items;
  }
  return [];
}

// ====================== 安装态 ======================

type InstallStatus = 'idle' | 'installing' | 'done' | 'conflict' | 'error';

interface InstallState {
  status: InstallStatus;
  message?: string;
}

// ====================== 主页面 ======================

export function ScriptMarketplace() {
  const navigate = useNavigate();
  const install = useUploadScriptFromUrl();

  const [searchRaw, setSearchRaw] = useState('');
  const search = useDebounce(searchRaw, 200);

  // 每个 slug 的安装态 + 当前正在安装的 slug(mutation 全局 isPending,这里细化到卡片)
  const [installState, setInstallState] = useState<Record<string, InstallState>>({});
  const [busySlug, setBusySlug] = useState<string | null>(null);

  const {
    data: scripts,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['hub-scripts', HUB_URL],
    queryFn: ({ signal }) => fetchHubScripts(signal),
    staleTime: 60_000,
    retry: 1,
  });

  const filtered = useMemo(() => {
    const list = scripts ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (s) =>
        s.slug.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q) ||
        s.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [scripts, search]);

  async function handleInstall(item: HubScriptItem, force = false) {
    setBusySlug(item.slug);
    setInstallState((m) => ({ ...m, [item.slug]: { status: 'installing' } }));
    try {
      await install.mutateAsync({
        zip_url: `${HUB_URL}/api/scripts/${item.slug}/bundle.zip`,
        force,
        // 货架 bundle 已由货架做过结构校验(zip 安全 + manifest schema + slug);
        // 此处仍会再跑一遍结构校验,但**跳过 sandbox dry-run**:成品脚本多需真实凭证
        // 才能跑通,用空 config dry-run 必然失败(与「扫描入库」同级,不做 dry-run 门禁)。
        dry_run: false,
      });
      setInstallState((m) => ({ ...m, [item.slug]: { status: 'done' } }));
      toast.success(`已安装「${item.name}」到管家`, {
        action: {
          label: '查看',
          onClick: () => navigate(`/scripts/${item.slug}`),
        },
      });
    } catch (err) {
      const e = err as UploadError | Error;
      const status = (e as UploadError).status;
      if (status === 409) {
        // 已存在 → 提供覆盖安装
        setInstallState((m) => ({
          ...m,
          [item.slug]: { status: 'conflict', message: '管家已有同名脚本' },
        }));
      } else {
        setInstallState((m) => ({
          ...m,
          [item.slug]: { status: 'error', message: e.message || '安装失败' },
        }));
        toast.error(`安装「${item.name}」失败:${e.message || '未知错误'}`);
      }
    } finally {
      setBusySlug(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader
        title="脚本市场"
        description={`从脚本货架一键安装到管家 · ${HUB_URL}`}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/scripts')}
            >
              <ArrowLeft className="size-4" strokeWidth={1.75} />
              <span className="ml-1.5 hidden sm:inline">返回脚本</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                className={cn('size-4', isFetching && 'animate-spin')}
                strokeWidth={1.75}
              />
              <span className="ml-1.5">刷新</span>
            </Button>
          </>
        }
      />

      {/* 搜索 */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            strokeWidth={1.75}
          />
          <Input
            value={searchRaw}
            onChange={(e) => setSearchRaw(e.target.value)}
            placeholder="搜索货架脚本名 / slug / 标签..."
            className="h-9 pl-8 text-sm"
          />
        </div>
        {scripts && scripts.length > 0 ? (
          <span className="text-xs text-muted-foreground">
            货架共 {scripts.length} 个脚本
          </span>
        ) : null}
      </div>

      {/* 加载 / 错误 / 空 / 网格 */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={`sk-${i}`}
              className="h-[240px] animate-pulse rounded-xl border border-border bg-muted/30"
            />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-xl border-2 border-dashed border-danger/30 bg-danger/5">
          <EmptyState
            icon={AlertCircle}
            title="无法连接脚本货架"
            description={
              `${(error as Error)?.message ?? '请求失败'} · 货架地址 ${HUB_URL}` +
              '。请确认货架在线,且已对本站点放行 CORS。'
            }
            action={
              <Button variant="outline" onClick={() => refetch()}>
                <RefreshCw className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">重试</span>
              </Button>
            }
          />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={search ? Search : PackageOpen}
            title={search ? '没有匹配的脚本' : '货架暂无脚本'}
            description={
              search ? '试试清空搜索词' : '货架还没有发布任何脚本'
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((item) => (
            <MarketplaceCard
              key={item.slug}
              item={item}
              state={installState[item.slug] ?? { status: 'idle' }}
              busy={busySlug === item.slug}
              anyBusy={busySlug !== null}
              onInstall={(force) => handleInstall(item, force)}
              onView={() => navigate(`/scripts/${item.slug}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ====================== 卡片 ======================

interface MarketplaceCardProps {
  item: HubScriptItem;
  state: InstallState;
  busy: boolean;
  anyBusy: boolean;
  onInstall: (force: boolean) => void;
  onView: () => void;
}

function MarketplaceCard({
  item,
  state,
  busy,
  anyBusy,
  onInstall,
  onView,
}: MarketplaceCardProps) {
  return (
    <div className="flex flex-col rounded-xl border border-border bg-card/60 p-4 transition-colors hover:border-border/80 hover:bg-card">
      {/* 头部:图标 + 名称 + 版本 */}
      <div className="mb-2 flex items-start gap-3">
        <HubIcon item={item} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-foreground">{item.name}</div>
          <div className="truncate font-mono text-[11px] text-muted-foreground/80">
            {item.slug}
          </div>
        </div>
        <Badge
          variant="outline"
          className="shrink-0 font-mono text-[10px] font-normal text-muted-foreground"
        >
          v{item.version}
        </Badge>
      </div>

      {/* 描述 */}
      <p className="mb-3 line-clamp-2 min-h-[2.5em] text-xs text-muted-foreground">
        {item.description || '暂无描述'}
      </p>

      {/* 标签 */}
      {item.tags.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1">
          {item.tags.slice(0, 4).map((t) => (
            <span
              key={t}
              className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
            >
              {t}
            </span>
          ))}
        </div>
      ) : null}

      {/* 元信息 */}
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-muted-foreground/80">
        <span className="flex items-center gap-1">
          <FileCode2 className="size-3" strokeWidth={1.75} />
          {item.file_count} 文件
        </span>
        <span>{formatBytes(item.size_bytes)}</span>
        <span className="flex items-center gap-1">
          <Download className="size-3" strokeWidth={1.75} />
          {item.download_count}
        </span>
        {item.author ? <span>· {item.author}</span> : null}
      </div>

      {/* 操作 */}
      <div className="mt-auto flex items-center gap-2 pt-1">
        <InstallButton state={state} busy={busy} disabled={anyBusy} onInstall={onInstall} />
        {state.status === 'done' ? (
          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={onView}>
            查看
          </Button>
        ) : item.homepage ? (
          <Button
            variant="ghost"
            size="icon"
            className="size-8 shrink-0"
            aria-label="主页"
            onClick={() => window.open(item.homepage!, '_blank', 'noopener,noreferrer')}
          >
            <ExternalLink className="size-3.5" strokeWidth={1.75} />
          </Button>
        ) : null}
      </div>

      {/* 冲突 / 错误提示 */}
      {state.status === 'conflict' ? (
        <p className="mt-2 text-[10.5px] text-warning">
          {state.message}，可点「覆盖安装」替换。
        </p>
      ) : state.status === 'error' ? (
        <p className="mt-2 line-clamp-2 text-[10.5px] text-danger">{state.message}</p>
      ) : null}
    </div>
  );
}

function InstallButton({
  state,
  busy,
  disabled,
  onInstall,
}: {
  state: InstallState;
  busy: boolean;
  disabled: boolean;
  onInstall: (force: boolean) => void;
}) {
  if (busy) {
    return (
      <Button size="sm" className="h-8 flex-1 text-xs" disabled>
        <Loader2 className="mr-1.5 size-3.5 animate-spin" strokeWidth={1.75} />
        安装中
      </Button>
    );
  }
  if (state.status === 'done') {
    return (
      <Button
        size="sm"
        variant="outline"
        className="h-8 flex-1 border-success/30 text-xs text-success"
        disabled
      >
        <CheckCircle2 className="mr-1.5 size-3.5" strokeWidth={1.75} />
        已安装
      </Button>
    );
  }
  if (state.status === 'conflict') {
    return (
      <Button
        size="sm"
        variant="outline"
        className="h-8 flex-1 border-warning/40 text-xs text-warning hover:text-warning"
        disabled={disabled}
        onClick={() => onInstall(true)}
      >
        <Download className="mr-1.5 size-3.5" strokeWidth={1.75} />
        覆盖安装
      </Button>
    );
  }
  return (
    <Button
      size="sm"
      className="h-8 flex-1 text-xs"
      disabled={disabled}
      onClick={() => onInstall(false)}
    >
      <Download className="mr-1.5 size-3.5" strokeWidth={1.75} />
      {state.status === 'error' ? '重试安装' : '安装'}
    </Button>
  );
}

function HubIcon({ item }: { item: HubScriptItem }) {
  const [broken, setBroken] = useState(false);
  if (item.has_icon && !broken) {
    return (
      <img
        src={`${HUB_URL}/api/scripts/${item.slug}/icon`}
        alt={item.name}
        className="size-9 shrink-0 rounded-md border border-border bg-background object-contain p-0.5"
        onError={() => setBroken(true)}
        draggable={false}
      />
    );
  }
  // 回落:slug 派生色 + 首字母
  let h = 0;
  for (let i = 0; i < item.slug.length; i += 1) h = (h * 31 + item.slug.charCodeAt(i)) | 0;
  const variant = (Math.abs(h) % 5) + 1;
  const first = item.name.trim()[0] ?? item.slug[0] ?? '·';
  return (
    <div
      className="flex size-9 shrink-0 items-center justify-center rounded-md text-sm font-medium"
      style={{
        background: `color-mix(in oklch, var(--chart-${variant}) 14%, transparent)`,
        color: `var(--chart-${variant})`,
      }}
      aria-hidden
    >
      {/[A-Za-z]/.test(first) ? first.toUpperCase() : first}
    </div>
  );
}

export default ScriptMarketplace;
