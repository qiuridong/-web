/**
 * Runs 数据 hooks + SSE 实时日志 hook
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.4(`/api/v1/runs/*`)
 *   - SSE 事件流:§ 2.4.1(stdout / stderr / status / ping / end)
 *   - 前端 wireframe:`进度/设计/前端UI设计.md` § 3.7、§ 3.8、§ 6.3
 *
 * Query keys:
 *   ['runs']                            — root
 *   ['runs', 'list', filter]            — 列表(不含 stdout/stderr)
 *   ['runs', 'detail', id]              — 详情(含完整 stdout/stderr)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { toast } from 'sonner';

import { apiClient } from '@/api/client';
import { formatError } from '@/lib/error';

// ====================== 类型 ======================

export type RunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failure'
  | 'error'
  | 'timeout'
  | 'cancelled';

export type RunTriggerType = 'manual' | 'scheduled' | 'retry' | 'api';

export interface RunListItem {
  id: number;
  instance_id: number;
  /** 后端列表响应中常带,详情也带 */
  instance?: { id?: number; name?: string };
  script_slug: string;
  script?: { slug?: string; name?: string };
  trigger_type: RunTriggerType;
  trigger_user_id?: number | null;
  status: RunStatus;
  exit_code?: number | null;
  result_message?: string | null;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  host?: string | null;
}

export interface RunDetail extends RunListItem {
  result_data_json?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  stdout_truncated?: boolean;
  stderr_truncated?: boolean;
  parent_run_id?: number | null;
}

export interface RunsFilter {
  instance_id?: number;
  script_slug?: string;
  status?: RunStatus;
  trigger_type?: RunTriggerType;
  started_after?: string;
  started_before?: string;
  /** 排序与限制,后端默认按 started_at DESC */
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
  limit?: number;
}

export interface CleanupPayload {
  before?: string;
  keep_days?: number;
}

// ====================== 内部工具 ======================

function unwrapList<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)) {
    return (raw as { items: T[] }).items;
  }
  return [];
}

function buildListPath(filter: RunsFilter): string {
  const search = new URLSearchParams();
  if (filter.instance_id !== undefined) search.set('instance_id', String(filter.instance_id));
  if (filter.script_slug) search.set('script_slug', filter.script_slug);
  if (filter.status) search.set('status', filter.status);
  if (filter.trigger_type) search.set('trigger_type', filter.trigger_type);
  if (filter.started_after) search.set('started_after', filter.started_after);
  if (filter.started_before) search.set('started_before', filter.started_before);
  if (filter.order) search.set('order', filter.order);
  if (filter.page) search.set('page', String(filter.page));
  if (filter.page_size) search.set('page_size', String(filter.page_size));
  if (filter.limit) search.set('limit', String(filter.limit));
  const qs = search.toString();
  return qs ? `/api/v1/runs?${qs}` : '/api/v1/runs';
}

async function fetchRuns(filter: RunsFilter, signal?: AbortSignal): Promise<RunListItem[]> {
  const path = buildListPath(filter);
  const { data, error, response } = await apiClient.GET(path as never, { signal } as never);
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return unwrapList<RunListItem>(data);
}

async function fetchRun(id: number, signal?: AbortSignal): Promise<RunDetail> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/runs/${id}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as RunDetail;
}

async function postCancel(id: number): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/runs/${id}/cancel` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function deleteCleanup(payload: CleanupPayload): Promise<{ deleted: number }> {
  const { data, error, response } = await apiClient.DELETE(
    '/api/v1/runs/cleanup' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? { deleted: 0 }) as { deleted: number };
}

// ====================== Query keys ======================

export const runsQueryKeys = {
  all: ['runs'] as const,
  list: (filter: RunsFilter = {}) => ['runs', 'list', filter] as const,
  detail: (id: number) => ['runs', 'detail', id] as const,
};

// ====================== Hooks ======================

export function useRuns(
  filter: RunsFilter = {},
  enabled = true,
): UseQueryResult<RunListItem[], Error> {
  return useQuery({
    queryKey: runsQueryKeys.list(filter),
    queryFn: ({ signal }) => fetchRuns(filter, signal),
    enabled,
    staleTime: 10_000,
  });
}

export function useRun(id: number | undefined): UseQueryResult<RunDetail, Error> {
  return useQuery({
    queryKey: runsQueryKeys.detail(id ?? -1),
    queryFn: ({ signal }) => fetchRun(id as number, signal),
    enabled: id !== undefined && id > 0,
    staleTime: 5_000,
  });
}

export function useCancelRun(): UseMutationResult<void, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => postCancel(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: runsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: runsQueryKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: ['instances'] });
      toast.success('已请求取消');
    },
  });
}

export function useCleanupRuns(): UseMutationResult<{ deleted: number }, Error, CleanupPayload> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => deleteCleanup(payload),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: runsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
      toast.success(`已清理 ${data.deleted} 条`);
    },
  });
}

// ====================== SSE Log Stream Hook ======================

export interface LogLine {
  /** 'stdout' | 'stderr' */
  stream: 'stdout' | 'stderr';
  line: string;
  /** 收到的时间戳 ms */
  ts: number;
}

export interface LogStreamStatus {
  status: RunStatus;
  exit_code?: number | null;
  duration_ms?: number | null;
}

export type LogStreamState = 'connecting' | 'open' | 'paused' | 'closed' | 'error';

export interface UseLogStreamOptions {
  /** 自动开始(默认 true);为 false 时需要手动 resume() */
  auto?: boolean;
  /** 每个 stream 最大缓存行数(防内存爆炸);默认 5000 */
  maxBufferLines?: number;
  /** 收到一条 stdout 行时回调(LogViewer 直接写 xterm 用) */
  onStdout?: (line: string) => void;
  /** 收到一条 stderr 行时回调(LogViewer 写带红色 ANSI 的版本) */
  onStderr?: (line: string) => void;
  /** 状态变化(running → success / error / timeout / cancelled) */
  onStatus?: (status: LogStreamStatus) => void;
  /** 服务端发送 event:end 时回调,流自动关闭 */
  onEnd?: () => void;
  /** 网络/解析错误回调 */
  onError?: (err: unknown) => void;
}

export interface UseLogStreamReturn {
  lines: LogLine[];
  status: LogStreamStatus | null;
  state: LogStreamState;
  pause: () => void;
  resume: () => void;
  close: () => void;
  /** 清空 lines 缓存(不影响 SSE 连接) */
  clear: () => void;
}

/**
 * useLogStream — 订阅 `/api/v1/runs/{id}/logs/stream`
 *
 * - 用 `@microsoft/fetch-event-source` 而非原生 EventSource(后者不支持 cookie + 自定义 header)
 * - 内部维护 lines 缓存,LogViewer 既可监听 onStdout/onStderr 实时写终端,也可读 lines 兜底
 * - lines 数 > maxBufferLines 时从头部丢弃,避免内存爆炸
 * - 组件 unmount / runId 变更 / close() 都会 abort connection
 */
export function useLogStream(
  runId: number | undefined,
  options: UseLogStreamOptions = {},
): UseLogStreamReturn {
  const {
    auto = true,
    maxBufferLines = 5000,
    onStdout,
    onStderr,
    onStatus,
    onEnd,
    onError,
  } = options;

  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<LogStreamStatus | null>(null);
  const [state, setState] = useState<LogStreamState>('connecting');

  const abortRef = useRef<AbortController | null>(null);
  const pausedRef = useRef<boolean>(!auto);
  /** 暂停期间缓存的行(恢复时一次性 flush) */
  const pendingRef = useRef<LogLine[]>([]);

  /** 把 callback 装进 ref,避免 effect 因 callback 引用变化重连 */
  const cbRef = useRef({ onStdout, onStderr, onStatus, onEnd, onError });
  cbRef.current = { onStdout, onStderr, onStatus, onEnd, onError };

  const pushLine = useCallback(
    (line: LogLine) => {
      setLines((prev) => {
        const next =
          prev.length >= maxBufferLines ? prev.slice(prev.length - maxBufferLines + 1) : prev;
        return [...next, line];
      });
    },
    [maxBufferLines],
  );

  const flushPending = useCallback(() => {
    if (pendingRef.current.length === 0) return;
    const pending = pendingRef.current;
    pendingRef.current = [];
    setLines((prev) => {
      const merged = [...prev, ...pending];
      return merged.length > maxBufferLines ? merged.slice(merged.length - maxBufferLines) : merged;
    });
    for (const line of pending) {
      if (line.stream === 'stdout') cbRef.current.onStdout?.(line.line);
      else cbRef.current.onStderr?.(line.line);
    }
  }, [maxBufferLines]);

  const close = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState('closed');
  }, []);

  const pause = useCallback(() => {
    pausedRef.current = true;
    setState('paused');
  }, []);

  const resume = useCallback(() => {
    pausedRef.current = false;
    flushPending();
    setState((s) => (s === 'paused' ? 'open' : s));
  }, [flushPending]);

  const clear = useCallback(() => {
    setLines([]);
    pendingRef.current = [];
  }, []);

  useEffect(() => {
    if (runId === undefined || runId <= 0) return;
    if (!auto) return; // 调用方手动 resume

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    pausedRef.current = false;
    setState('connecting');

    fetchEventSource(`/api/v1/runs/${runId}/logs/stream`, {
      signal: ctrl.signal,
      credentials: 'include',
      headers: {
        Accept: 'text/event-stream',
        'X-Requested-With': 'fetch',
      },
      openWhenHidden: true,
      onopen: async (resp) => {
        if (resp.ok) {
          setState('open');
          return;
        }
        setState('error');
        const msg = `SSE 连接失败 (HTTP ${resp.status})`;
        cbRef.current.onError?.(new Error(msg));
        throw new Error(msg);
      },
      onmessage: (ev) => {
        const line: LogLine = { stream: 'stdout', line: ev.data, ts: Date.now() };
        switch (ev.event) {
          case 'stdout':
            line.stream = 'stdout';
            if (pausedRef.current) {
              pendingRef.current.push(line);
            } else {
              pushLine(line);
              cbRef.current.onStdout?.(ev.data);
            }
            break;
          case 'stderr':
            line.stream = 'stderr';
            if (pausedRef.current) {
              pendingRef.current.push(line);
            } else {
              pushLine(line);
              cbRef.current.onStderr?.(ev.data);
            }
            break;
          case 'status':
            try {
              const s = JSON.parse(ev.data) as LogStreamStatus;
              setStatus(s);
              cbRef.current.onStatus?.(s);
            } catch {
              // 容错:无法解析就忽略
            }
            break;
          case 'ping':
            // keep-alive,不处理
            break;
          case 'end':
            cbRef.current.onEnd?.();
            ctrl.abort();
            setState('closed');
            break;
          default:
            // 兼容服务端发送默认 message(无 event 字段)
            if (!ev.event) {
              if (pausedRef.current) {
                pendingRef.current.push(line);
              } else {
                pushLine(line);
                cbRef.current.onStdout?.(ev.data);
              }
            }
            break;
        }
      },
      onerror: (err) => {
        setState('error');
        cbRef.current.onError?.(err);
        // 不抛 → fetchEventSource 会自动重连;抛 → 终止
        throw err;
      },
      onclose: () => {
        setState((s) => (s === 'error' ? 'error' : 'closed'));
      },
    }).catch(() => {
      // onerror 抛出后这里会进 catch;状态已置为 error,不重复处理
    });

    return () => {
      ctrl.abort();
      abortRef.current = null;
    };
  }, [runId, auto, maxBufferLines, pushLine]);

  return { lines, status, state, pause, resume, close, clear };
}
