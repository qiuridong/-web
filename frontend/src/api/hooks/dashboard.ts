/**
 * Dashboard 数据 hooks(TanStack Query 5)
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.7(`/api/v1/dashboard/*` 4 端点)
 *   - 前端 wireframe / 状态:`进度/设计/前端UI设计.md` § 3.3、§ 5.2
 *
 * Query Factory 模式;查询 key 全部以 `['dashboard', ...]` 开头便于批量 invalidate。
 *
 * TODO(Batch 3 / Backend-Scripts-API):后端 dashboard router 仍是 stub;
 * 接入真实 API 后可移除 fallbackData(改成依赖 useQuery 的 isPending)。
 *
 * 当前策略(stub 阶段):
 *   - 真请求由 apiClient 发出
 *   - 失败(404 / network)走 catch → 返回 mock,使 UI 有内容
 *   - 一旦后端接通,fallback 路径自动失效,真数据接管
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import { isUnauthorized } from '@/lib/error';
import {
  mockOverview,
  mockUpcoming,
  mockRecentFailures,
  mockTimeline,
  type DashboardOverview,
  type UpcomingItem,
  type RecentFailureItem,
  type TimelineRow,
} from '@/api/mocks/dashboard.mocks';

/**
 * 内部:统一执行带 fallback 的 GET。
 *
 * - 401/403 直接抛(由 client.ts middleware 跳登录,不走 mock)
 * - 其余错误 → 返回 mock,console.warn 记录(不打扰用户)
 */
async function fetchWithFallback<T>(
  path: string,
  fallback: T,
  signal?: AbortSignal,
): Promise<T> {
  try {
    const { data, error, response } = await apiClient.GET(path as never, { signal } as never);
    if (error) {
      // 401/403 已被 middleware 派事件 + 自动跳登录,这里继续抛阻断后续
      if (response && (response.status === 401 || response.status === 403)) {
        throw error;
      }
      console.warn(`[dashboard] ${path} 后端错误,使用 mock:`, error);
      return fallback;
    }
    return (data as T) ?? fallback;
  } catch (err) {
    if (isUnauthorized(err)) throw err;
    console.warn(`[dashboard] ${path} 异常,使用 mock:`, err);
    return fallback;
  }
}

/* ============== overview =============== */

/**
 * 后端 § 2.7 真实返回(MVP-2 实测):仅含 scripts / instances / runs_24h /
 * success_rate_24h / success_rate_7d 5 个字段;MVP-1 mock 多了 sparkline_7d_* /
 * notifications_24h / next_run_at — 这些字段后端 schema 暂不返回(MVP-3 补)。
 *
 * 此处 adapter 把后端真数据**补齐**为 mock 的完整 shape,让 KpiCard 等组件不崩
 * (`undefined.map(...)` 是 dashboard 顶级首页崩溃的根因)。
 */
function adaptOverview(raw: Partial<DashboardOverview> | DashboardOverview): DashboardOverview {
  const r = raw as Partial<DashboardOverview>;
  return {
    scripts: r.scripts ?? { total: 0, enabled: 0 },
    instances: r.instances ?? { total: 0, enabled: 0, paused: 0 },
    runs_24h: r.runs_24h ?? { total: 0, success: 0, failure: 0, running: 0 },
    success_rate_24h: r.success_rate_24h ?? 0,
    success_rate_7d: r.success_rate_7d ?? 0,
    // 以下字段后端暂未返回(MVP-3 补);先用安全默认避免 .map(undefined) 崩
    sparkline_7d_success: r.sparkline_7d_success ?? [],
    sparkline_7d_runs: r.sparkline_7d_runs ?? [],
    notifications_24h: r.notifications_24h ?? 0,
    next_run_at: r.next_run_at ?? null,
  };
}

export function useDashboardOverview(): UseQueryResult<DashboardOverview, Error> {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: async ({ signal }) => {
      const raw = await fetchWithFallback<DashboardOverview>(
        '/api/v1/dashboard/overview',
        mockOverview,
        signal,
      );
      return adaptOverview(raw);
    },
    refetchInterval: 30_000,
    placeholderData: (prev) => prev ?? mockOverview,
  });
}

/* ============== upcoming =============== */

export function useDashboardUpcoming(limit = 5): UseQueryResult<UpcomingItem[], Error> {
  return useQuery({
    queryKey: ['dashboard', 'upcoming', { limit }],
    queryFn: ({ signal }) =>
      fetchWithFallback<UpcomingItem[]>(
        `/api/v1/dashboard/upcoming?limit=${limit}`,
        mockUpcoming.slice(0, limit),
        signal,
      ),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev ?? mockUpcoming.slice(0, limit),
  });
}

/* ============== recent failures =============== */

export function useDashboardRecentFailures(limit = 5): UseQueryResult<RecentFailureItem[], Error> {
  return useQuery({
    queryKey: ['dashboard', 'recent-failures', { limit }],
    queryFn: ({ signal }) =>
      fetchWithFallback<RecentFailureItem[]>(
        `/api/v1/dashboard/recent-failures?limit=${limit}`,
        mockRecentFailures.slice(0, limit),
        signal,
      ),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev ?? mockRecentFailures.slice(0, limit),
  });
}

/* ============== timeline ===============
 * 设计稿 § 2.7:`?bucket=hour|day&days=7` 返回 [{ts, success, failure, error, timeout}]。
 * 但 § 3.3 wireframe 的 Timeline section 是"实时活动条目流"(每条 = 一次 run),
 * 与 timeline-API(分桶聚合)语义不同。
 *
 * 这里 useDashboardTimeline 提供的是"实时活动 run 列表",mock 直接给 run 数组。
 * 后端接入时,应使用 `/api/v1/runs?limit=20&order=desc` 而非 /dashboard/timeline。
 * 暂时保持 endpoint 名一致,后续 Batch 3 重命名 hook 即可(避免破坏调用方)。
 */

/** 后端 `/api/v1/runs` 列表 RunListItem 类型(仅本文件用)。 */
interface BackendRunListItem {
  id: number;
  instance_id: number;
  script_slug: string;
  trigger_type: 'manual' | 'scheduled' | 'retry' | 'api';
  status: TimelineRow['status'];
  result_message?: string | null;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
}

/** 后端 RunListItem → 前端 TimelineRow(字段名/缺省补全)。 */
function runToTimelineRow(r: BackendRunListItem): TimelineRow {
  return {
    run_id: r.id,
    timestamp: r.started_at,
    script_slug: r.script_slug,
    script_name: r.script_slug, // 后端 list 不带 script_name,fallback 用 slug
    instance_id: r.instance_id,
    instance_name: `#${r.instance_id}`, // 同上,fallback
    status: r.status,
    duration_ms: r.duration_ms ?? null,
    trigger_type: r.trigger_type,
    result_message: r.result_message ?? null,
  };
}

export function useDashboardTimeline(limit = 20): UseQueryResult<TimelineRow[], Error> {
  return useQuery({
    queryKey: ['dashboard', 'timeline', { limit }],
    queryFn: async ({ signal }) => {
      // 后端 GET /runs 返 {items, total, page, page_size},不是裸数组
      const raw = await fetchWithFallback<unknown>(
        `/api/v1/runs?page_size=${limit}`,
        { items: mockTimeline.slice(0, limit) } as unknown,
        signal,
      );
      // 兼容 3 种形态:已是 TimelineRow[](mock)/ {items: BackendRunListItem[]}(真后端)/ undefined
      if (Array.isArray(raw)) {
        // mock fallback 路径:数据已是 TimelineRow[]
        return raw as TimelineRow[];
      }
      const wrapped = raw as { items?: BackendRunListItem[] } | null | undefined;
      const items = Array.isArray(wrapped?.items) ? wrapped!.items : [];
      // 检查首项:已是 TimelineRow(mock 通过 {items: mockTimeline} 包装)还是 BackendRunListItem
      const first = items[0] as unknown;
      if (first && typeof first === 'object' && 'run_id' in first) {
        return items as unknown as TimelineRow[];
      }
      return items.map(runToTimelineRow);
    },
    refetchInterval: 30_000,
    placeholderData: (prev) => prev ?? mockTimeline.slice(0, limit),
  });
}
