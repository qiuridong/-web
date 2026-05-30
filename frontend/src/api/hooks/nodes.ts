/**
 * Nodes 数据 hooks(MVP-1 远程 agent)
 *
 * 后端 API:`backend/app/api/v1/nodes.py`
 * 设计稿:`进度/设计/远程VPS脚本执行调研.md` § 7
 *
 * Query keys:
 *   ['nodes']                    — root,创建/删除/regenerate 后 invalidate
 *   ['nodes', 'list']            — 列表
 *   ['nodes', 'detail', id]      — 详情
 *
 * 注意:
 *   - schema.d.ts 还没有 nodes 类型,本文件用 apiClient.GET<any> + 手写 TS 接口
 *   - create / regenerate-token 返回明文 token,**只展示一次**,前端组件要 modal 显示给用户复制
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { toast } from 'sonner';

import { apiClient } from '@/api/client';
import { formatError } from '@/lib/error';

// ====================== 类型 ======================

export interface NodeListItem {
  id: number;
  slug: string;
  name: string | null;
  description: string | null;
  is_local: boolean;
  last_seen_at: string | null;
  version: string | null;
  metadata: Record<string, unknown>;
  enabled: boolean;
  online: boolean;
  created_at: string;
  updated_at: string;
}

export interface NodeDetail extends NodeListItem {
  /** agent 上报的已部署脚本 {slug: {sha256, deployed_at}} */
  deployed_scripts?: Record<string, { sha256?: string; deployed_at?: string }>;
  /** 待 agent 执行的指令(sync 拉取 / delete 删除) */
  pending_actions?: { sync?: string[]; delete?: string[] };
}

export interface NodeListResponse {
  items: NodeListItem[];
  total: number;
}

export interface NodeCreate {
  slug: string;
  name?: string | null;
  description?: string | null;
}

export interface NodeUpdate {
  name?: string | null;
  description?: string | null;
  enabled?: boolean;
}

/** 创建响应 — 含一次性明文 token */
export interface NodeCreateResponse {
  node: NodeDetail;
  token: string;
}

export interface NodeTokenResponse {
  token: string;
}

// ====================== Fetch helpers ======================

async function fetchNodes(signal?: AbortSignal): Promise<NodeListResponse> {
  const { data, error, response } = await apiClient.GET(
    '/api/v1/nodes' as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  const raw = (data ?? { items: [], total: 0 }) as Partial<NodeListResponse>;
  return {
    items: Array.isArray(raw.items) ? raw.items : [],
    total: raw.total ?? 0,
  };
}

async function fetchNodeDetail(id: number, signal?: AbortSignal): Promise<NodeDetail> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/nodes/${id}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return data as unknown as NodeDetail;
}

async function createNode(payload: NodeCreate): Promise<NodeCreateResponse> {
  const { data, error, response } = await apiClient.POST(
    '/api/v1/nodes' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return data as unknown as NodeCreateResponse;
}

async function updateNode(id: number, payload: NodeUpdate): Promise<NodeDetail> {
  const { data, error, response } = await apiClient.PATCH(
    `/api/v1/nodes/${id}` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return data as unknown as NodeDetail;
}

async function deleteNode(id: number): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    `/api/v1/nodes/${id}` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function regenerateToken(id: number): Promise<NodeTokenResponse> {
  const { data, error, response } = await apiClient.POST(
    `/api/v1/nodes/${id}/regenerate-token` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return data as unknown as NodeTokenResponse;
}

async function uninstallNodeScript(nodeId: number, slug: string): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/nodes/${nodeId}/deployed-scripts/${encodeURIComponent(slug)}/uninstall` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

// ====================== Query keys ======================

export const nodesQueryKeys = {
  all: ['nodes'] as const,
  list: () => ['nodes', 'list'] as const,
  detail: (id: number) => ['nodes', 'detail', id] as const,
};

// ====================== Hooks ======================

/** GET /api/v1/nodes — 节点列表(含 online 派生字段) */
export function useNodes(): UseQueryResult<NodeListResponse, Error> {
  return useQuery({
    queryKey: nodesQueryKeys.list(),
    queryFn: ({ signal }) => fetchNodes(signal),
    staleTime: 15_000,
    refetchInterval: 30_000, // 每 30s 刷新 online 状态
  });
}

/** GET /api/v1/nodes/{id} — 节点详情 */
export function useNode(id: number | undefined): UseQueryResult<NodeDetail, Error> {
  return useQuery({
    queryKey: nodesQueryKeys.detail(id ?? 0),
    queryFn: ({ signal }) => fetchNodeDetail(id as number, signal),
    enabled: !!id,
    staleTime: 15_000,
  });
}

/** POST /api/v1/nodes — 创建节点(返回一次性明文 token) */
export function useCreateNode(): UseMutationResult<NodeCreateResponse, Error, NodeCreate> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => createNode(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.all });
      // 不直接 toast(由 NodeList Dialog 显示 token);避免 toast 闪一下盖住关键信息
    },
  });
}

/** PATCH /api/v1/nodes/{id} — 改 name/description/enabled */
export function useUpdateNode(): UseMutationResult<NodeDetail, Error, { id: number; payload: NodeUpdate }> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => updateNode(id, payload),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.all });
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.detail(id) });
      toast.success('节点已更新');
    },
  });
}

/** DELETE /api/v1/nodes/{id} */
export function useDeleteNode(): UseMutationResult<void, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => deleteNode(id),
    onSuccess: (_, id) => {
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.all });
      qc.removeQueries({ queryKey: nodesQueryKeys.detail(id) });
      toast.success('节点已删除');
    },
  });
}

/** POST /api/v1/nodes/{id}/regenerate-token */
export function useRegenerateNodeToken(): UseMutationResult<NodeTokenResponse, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => regenerateToken(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.all });
      // token 由 NodeList Dialog 显示
    },
  });
}

/** POST /api/v1/nodes/{id}/deployed-scripts/{slug}/uninstall — 下发删除指令给 agent */
export function useUninstallNodeScript(): UseMutationResult<
  void,
  Error,
  { nodeId: number; slug: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, slug }) => uninstallNodeScript(nodeId, slug),
    onSuccess: (_, { nodeId }) => {
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.detail(nodeId) });
      void qc.invalidateQueries({ queryKey: nodesQueryKeys.all });
      toast.success('已下发删除指令,agent 下次拉取(最长 30s)时删除并回报');
    },
  });
}
