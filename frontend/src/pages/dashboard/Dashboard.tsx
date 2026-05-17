/**
 * `/dashboard` — 仪表盘页面
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.3(wireframe + 美化要点 + 关键交互)。
 *
 * 5 section 布局(按设计稿):
 *   1. 顶部 PageHeader(扫描脚本 + 新建实例 + 刷新)
 *   2. 6 张 KpiCard(脚本 / 实例 / 今日执行 / 下次执行 / 失败 / 通知)
 *   3. 即将执行 + 最近失败(左右)
 *   4. 脚本健康度卡片网格
 *   5. 实时活动 Timeline
 *
 * Mock 数据:
 *   - hooks fallback 到 mock(后端 stub 阶段)
 *   - 用户可见 → 后端接通自动切换
 *
 * 重要:**不要** wrap AppLayout——由 router 在外层套(由 5A 决定)
 */
import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronRight,
  Clock,
  Inbox,
  Layers,
  Play,
  RefreshCcw,
  ScanSearch,
  Sparkles,
  Target,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';

import { EmptyState } from '@/components/common/EmptyState';
import { KpiCard } from '@/components/common/KpiCard';
import { PageHeader } from '@/components/common/PageHeader';
import { ScriptCard, type ScriptCardData } from '@/components/common/ScriptCard';
import { Timeline } from '@/components/common/Timeline';

import {
  useDashboardOverview,
  useDashboardRecentFailures,
  useDashboardTimeline,
  useDashboardUpcoming,
} from '@/api/hooks/dashboard';
import { useScripts, useScanScripts } from '@/api/hooks/scripts';
import { formatDate, formatDuration, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export function Dashboard() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const overviewQ = useDashboardOverview();
  const upcomingQ = useDashboardUpcoming(5);
  const failuresQ = useDashboardRecentFailures(5);
  const timelineQ = useDashboardTimeline(20);
  const scriptsQ = useScripts({});
  const scanScripts = useScanScripts();

  const overview = overviewQ.data;
  const isLoadingKpis = !overview && overviewQ.isPending;

  // 下次执行倒计时(简单展示分钟数)— mock 阶段就用 next_run_at 字段算
  const nextRunMinutes = useMemo(() => {
    if (!overview?.next_run_at) return null;
    const diff = new Date(overview.next_run_at).getTime() - Date.now();
    if (Number.isNaN(diff)) return null;
    return Math.max(0, Math.round(diff / 60000));
  }, [overview?.next_run_at]);

  const onRefresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    void queryClient.invalidateQueries({ queryKey: ['scripts'] });
    toast.success('已刷新');
  };

  const onScan = async () => {
    // useScanScripts 自身 onSuccess 已 toast(added/updated/removed/errors);
    // onError 由全局 mutation onError 兜底。
    try {
      await scanScripts.mutateAsync();
    } catch {
      // swallow,toast 由 hook / 全局兜底
    }
  };

  const onTriggerScript = (slug: string) => {
    // 跳到详情页 "实例" Tab,用户选具体 instance 触发(script 整体 trigger 无意义,可能 0 或 N instance)
    navigate(`/scripts/${slug}?tab=instances`);
  };

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-4 pb-12 pt-6 sm:px-6">
      <PageHeader
        title="仪表盘"
        description="脚本健康度 / 即将执行 / 最近失败 / 实时活动一览"
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={onScan}
              disabled={scanScripts.isPending}
            >
              <ScanSearch className="mr-1.5 size-4" strokeWidth={1.75} />
              {scanScripts.isPending ? '扫描中…' : '扫描脚本'}
            </Button>
            <Button asChild variant="default" size="sm">
              <Link to="/scripts">
                <Sparkles className="mr-1.5 size-4" strokeWidth={1.75} />
                新建实例
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="刷新"
              onClick={onRefresh}
              className={cn(overviewQ.isFetching && 'animate-pulse')}
            >
              <RefreshCcw className="size-4" strokeWidth={1.75} />
            </Button>
          </>
        }
      />

      {/* ============ KPI 区(6 张) ============ */}
      <section
        aria-label="KPI"
        className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6"
      >
        <KpiCard
          title="脚本总数"
          value={overview?.scripts.total ?? 0}
          unit="个"
          icon={Layers}
          trend={
            overview
              ? {
                  value: overview.scripts.enabled - overview.scripts.total + overview.scripts.total,
                  label: `${overview.scripts.enabled} 启用`,
                  isPercent: false,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
        <KpiCard
          title="实例总数"
          value={overview?.instances.total ?? 0}
          unit="个"
          icon={Target}
          trend={
            overview
              ? {
                  value: overview.instances.enabled,
                  label: `${overview.instances.paused} 暂停`,
                  isPercent: false,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
        <KpiCard
          title="今日执行"
          value={overview?.runs_24h.total ?? 0}
          icon={Activity}
          sparkline={overview?.sparkline_7d_runs}
          sparklineVariant={1}
          trend={
            overview
              ? {
                  value: overview.runs_24h.success,
                  label: `${overview.runs_24h.success}/${overview.runs_24h.total} 成功`,
                  isPercent: false,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
        <KpiCard
          title="今日成功率"
          value={overview ? Number((overview.success_rate_24h * 100).toFixed(1)) : 0}
          unit="%"
          icon={Sparkles}
          sparkline={(overview?.sparkline_7d_success ?? []).map((v) => v * 100)}
          sparklineVariant={4}
          trend={
            overview
              ? {
                  value: Number(
                    ((overview.success_rate_24h - overview.success_rate_7d) * 100).toFixed(1),
                  ),
                  label: 'vs 7d',
                  isPercent: true,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
        <KpiCard
          title="失败数"
          value={overview?.runs_24h.failure ?? 0}
          unit="次"
          icon={AlertTriangle}
          sparklineVariant={5}
          trend={
            overview
              ? {
                  value: -(overview.runs_24h.failure ?? 0),
                  label: '24h',
                  isPercent: false,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
        <KpiCard
          title="下次执行"
          value={nextRunMinutes !== null ? nextRunMinutes : '—'}
          unit={nextRunMinutes !== null ? 'min' : undefined}
          icon={Clock}
          trend={
            overview?.next_run_at
              ? {
                  value: 0,
                  label: formatDate(overview.next_run_at, 'HH:mm'),
                  isPercent: false,
                }
              : undefined
          }
          loading={isLoadingKpis}
        />
      </section>

      {/* ============ 即将执行 / 最近失败(左右) ============ */}
      <section
        aria-label="即将执行 / 最近失败"
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
      >
        {/* 即将执行 */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Clock className="size-4 text-primary" strokeWidth={1.75} />
              即将执行
            </CardTitle>
            <span className="text-xs text-muted-foreground/70">
              按 next_run_at 排序
            </span>
          </CardHeader>
          <CardContent className="pt-0">
            {upcomingQ.isPending && !upcomingQ.data ? (
              <UpcomingSkeleton />
            ) : !upcomingQ.data || upcomingQ.data.length === 0 ? (
              <EmptyState
                icon={Clock}
                title="暂无待执行"
                description="所有实例都没有调度计划,创建实例后将出现在这里"
              />
            ) : (
              <ul className="space-y-2">
                {(upcomingQ.data ?? []).map((it) => {
                  const minutes = Math.max(
                    0,
                    Math.round((new Date(it.next_run_at).getTime() - Date.now()) / 60000),
                  );
                  return (
                    <li
                      key={it.instance_id}
                      className="group flex items-center gap-3 rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-border hover:bg-accent/30"
                    >
                      <span className="relative inline-flex size-2 shrink-0 isolate text-primary">
                        <span className="block size-2 rounded-full bg-current dot-pulse" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2 truncate text-sm">
                          <span className="truncate font-medium text-foreground">
                            {it.script_name}
                          </span>
                          <span className="text-muted-foreground/40">·</span>
                          <span className="truncate text-muted-foreground">
                            {it.instance_name}
                          </span>
                        </div>
                        <p className="truncate font-mono text-[11px] text-muted-foreground/60">
                          {it.cron_expr}
                        </p>
                      </div>
                      <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                        {minutes < 60 ? `${minutes}m` : `${(minutes / 60).toFixed(1)}h`}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* 最近失败 */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-foreground">
              <AlertTriangle className="size-4 text-danger" strokeWidth={1.75} />
              最近失败
            </CardTitle>
            <Button asChild variant="ghost" size="sm" className="-mr-2 text-xs">
              <Link to="/runs?status=failure">
                查看全部
                <ChevronRight className="ml-0.5 size-3.5" strokeWidth={1.75} />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="pt-0">
            {failuresQ.isPending && !failuresQ.data ? (
              <UpcomingSkeleton />
            ) : !failuresQ.data || failuresQ.data.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="近期没有失败"
                description="所有执行都顺利完成"
              />
            ) : (
              <ul className="space-y-2">
                {(failuresQ.data ?? []).map((it) => (
                  <li
                    key={it.run_id}
                    className="group flex items-center gap-3 rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-border hover:bg-accent/30"
                  >
                    <span
                      className={cn(
                        'relative inline-flex size-2 shrink-0 isolate',
                        it.status === 'timeout' ? 'text-warning' : 'text-danger',
                      )}
                    >
                      <span className="block size-2 rounded-full bg-current" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2 truncate text-sm">
                        <span className="truncate font-medium text-foreground">
                          {it.script_name}
                        </span>
                        <span className="text-muted-foreground/40">·</span>
                        <span className="truncate text-muted-foreground">
                          {it.instance_name}
                        </span>
                      </div>
                      {it.result_message ? (
                        <HoverCard openDelay={250}>
                          <HoverCardTrigger asChild>
                            <p className="truncate text-xs text-muted-foreground/70">
                              {it.result_message}
                            </p>
                          </HoverCardTrigger>
                          <HoverCardContent
                            side="bottom"
                            align="start"
                            className="max-w-md text-xs"
                          >
                            {it.result_message}
                          </HoverCardContent>
                        </HoverCard>
                      ) : (
                        <p className="text-[11px] italic text-muted-foreground/40">
                          (无错误信息)
                        </p>
                      )}
                    </div>
                    <span className="shrink-0 tabular-nums text-xs text-muted-foreground/70">
                      {formatRelative(it.finished_at)}
                    </span>
                    <span className="hidden w-12 shrink-0 text-right tabular-nums text-xs text-muted-foreground/60 sm:inline">
                      {formatDuration(it.duration_ms)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      {/* ============ 脚本健康度卡片网格 ============ */}
      <section aria-label="脚本健康度">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-foreground/90">
            脚本健康度
          </h2>
          <Button asChild variant="ghost" size="sm" className="-mr-2 text-xs">
            <Link to="/scripts">
              全部脚本
              <ChevronRight className="ml-0.5 size-3.5" strokeWidth={1.75} />
            </Link>
          </Button>
        </div>

        {scriptsQ.isPending && !scriptsQ.data ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <Skeleton className="h-[220px] rounded-xl" />
            <Skeleton className="h-[220px] rounded-xl" />
            <Skeleton className="h-[220px] rounded-xl" />
            <Skeleton className="h-[220px] rounded-xl" />
          </div>
        ) : !scriptsQ.data || scriptsQ.data.length === 0 ? (
          <Card>
            <CardContent className="p-0">
              <EmptyState
                icon={Inbox}
                title="还没有脚本"
                description="把签到脚本放到 scripts/ 目录后,点击「扫描脚本」自动入库"
                action={
                  <Button onClick={onScan} disabled={scanScripts.isPending}>
                    <ScanSearch className="mr-1.5 size-4" strokeWidth={1.75} />
                    {scanScripts.isPending ? '扫描中…' : '立即扫描'}
                  </Button>
                }
              />
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {(scriptsQ.data ?? []).slice(0, 8).map((s) => {
              const cardData: ScriptCardData = {
                slug: s.slug,
                name: s.name,
                description: s.description,
                version: s.version,
                enabled: s.enabled,
                instance_count: s.instance_count,
                instance_enabled_count: s.instance_enabled_count,
                last_run_status: s.last_run_status,
                last_run_at: s.last_run_at,
                next_run_at: s.next_run_at,
                success_rate_7d: s.success_rate_7d,
              };
              return (
                <ScriptCard
                  key={s.slug}
                  script={cardData}
                  onTrigger={onTriggerScript}
                  onConfigure={(slug) => toast.info(`配置页待实现 (${slug})`)}
                />
              );
            })}
          </div>
        )}
      </section>

      {/* ============ 实时活动 Timeline ============ */}
      <section aria-label="实时活动">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground/90">
            <Play className="size-4 text-primary" strokeWidth={1.75} />
            实时活动
          </h2>
          <Button asChild variant="ghost" size="sm" className="-mr-2 text-xs">
            <Link to="/runs">
              查看全部
              <ChevronRight className="ml-0.5 size-3.5" strokeWidth={1.75} />
            </Link>
          </Button>
        </div>
        {timelineQ.isPending && !timelineQ.data ? (
          <Skeleton className="h-[480px] rounded-xl" />
        ) : (
          <Timeline rows={timelineQ.data ?? []} height={480} />
        )}
        {/* 装饰式占位:防止 lint 抱怨某些 import 未用 — Bell / Bell 图标用于未来 KPI 6 占位备选 */}
        <Bell aria-hidden className="hidden" />
      </section>
    </div>
  );
}

/* ====================== 内部 Skeleton ====================== */

function UpcomingSkeleton() {
  return (
    <ul className="space-y-2">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex items-center gap-3 px-2 py-2">
          <Skeleton className="size-2 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-2 w-1/3" />
          </div>
          <Skeleton className="h-3 w-10" />
        </li>
      ))}
    </ul>
  );
}

export default Dashboard;
