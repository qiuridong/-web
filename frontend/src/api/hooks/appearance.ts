/**
 * 应用外观品牌设置 hook
 *
 * 后端契约:`GET/PUT /api/v1/settings/appearance` 通用 settings KV 端点
 * value 是 JSON 对象,包含站点标题 / Logo 文本 / Logo 图(base64) / 背景图 等
 *
 * 设计选择:**所有外观字段塞进一个 dict**(setting key='appearance'),
 * 整体读写,简化 API + 缓存。图片走 base64 data URL 内联存(单字段 < 3 MB)。
 *
 * 默认值与后端 settings_service.DEFAULT_SETTINGS['appearance'] 对齐 — 任何
 * 字段缺失时本 hook 用默认值兜底(避免新部署的实例首访 sidebar logo 不显示)。
 *
 * AppLayout 在 root 订阅本 hook,实时把 setting 注入 DOM:
 * - site_title → document.title
 * - sidebar_logo_text → 侧栏顶部品牌字
 * - logo_image_data_url → 侧栏顶部图标(覆盖默认"签"字)
 * - background_image_data_url → main 容器 background-image
 * - background_blur → main backdrop-filter: blur()
 * - background_opacity → main background overlay alpha
 * - background_blend_mode → CSS background-blend-mode
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

export interface AppearanceData {
  /** 网站标题(浏览器 tab + 侧栏品牌名)*/
  site_title: string;
  /** 副标题 / 版本号(侧栏品牌名下方小字)*/
  site_subtitle: string;
  /** 侧栏顶部图标位的文本(无 logo 图时显示);1-2 字符最佳 */
  sidebar_logo_text: string;
  /** Logo 图 base64 data URL(`data:image/png;base64,...`);空字符串 = 不用 */
  logo_image_data_url: string;
  /** 背景图 base64 data URL;空字符串 = 不用 */
  background_image_data_url: string;
  /** 背景图模糊度 0-40 px */
  background_blur: number;
  /** 背景图叠加的暗角(亮色)/ 透明度 0-1 */
  background_opacity: number;
  /** CSS background-blend-mode(normal / multiply / overlay / etc)*/
  background_blend_mode: string;
}

export const DEFAULT_APPEARANCE: AppearanceData = {
  site_title: '签到管家',
  site_subtitle: '',
  sidebar_logo_text: '签',
  logo_image_data_url: '',
  background_image_data_url: '',
  background_blur: 0,
  background_opacity: 0.3,
  background_blend_mode: 'normal',
};

// ====================== Fetch helpers ======================

interface SettingValue {
  key: string;
  value: unknown;
}

async function fetchAppearance(signal?: AbortSignal): Promise<AppearanceData> {
  const { data, error, response } = await apiClient.GET(
    '/api/v1/settings/appearance' as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  const raw = (data ?? { value: null }) as SettingValue;
  const partial =
    raw.value && typeof raw.value === 'object'
      ? (raw.value as Partial<AppearanceData>)
      : {};
  // 用默认值兜底缺失字段(向后兼容老 setting 没新字段)
  return { ...DEFAULT_APPEARANCE, ...partial };
}

async function putAppearance(data: AppearanceData): Promise<AppearanceData> {
  const { error, response } = await apiClient.PUT(
    '/api/v1/settings/appearance' as never,
    { body: { value: data } } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return data;
}

// ====================== Query keys ======================

export const appearanceQueryKeys = {
  current: ['settings', 'appearance'] as const,
};

// ====================== Hooks ======================

/**
 * 读取当前 appearance 设置。
 *
 * `staleTime: Infinity` — 这是站点级配置,改动罕见 + invalidate by mutation,
 * 避免每次组件 mount 都重 fetch(2 张图 base64 可能几百 KB)。
 */
export function useAppearance(): UseQueryResult<AppearanceData, Error> {
  return useQuery({
    queryKey: appearanceQueryKeys.current,
    queryFn: ({ signal }) => fetchAppearance(signal),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useUpdateAppearance(): UseMutationResult<
  AppearanceData,
  Error,
  AppearanceData
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: putAppearance,
    onSuccess: (data) => {
      qc.setQueryData(appearanceQueryKeys.current, data);
      toast.success('外观设置已保存');
    },
    onError: (err) => {
      toast.error(`保存失败:${err.message}`);
    },
  });
}

// ====================== 工具函数 ======================

/**
 * 把 File 转成 base64 data URL(用于上传 logo / 背景图)。
 *
 * @param maxBytes 文件大小上限,超过 throw(默认 2 MiB)
 * @throws 文件类型不是 image/* 或超过上限
 */
export function fileToDataUrl(
  file: File,
  maxBytes = 2 * 1024 * 1024,
): Promise<string> {
  if (!file.type.startsWith('image/')) {
    return Promise.reject(new Error(`文件类型不是图片(${file.type || '未知'})`));
  }
  if (file.size > maxBytes) {
    return Promise.reject(
      new Error(`图片大小 ${(file.size / 1024).toFixed(0)} KB 超过上限 ${(maxBytes / 1024 / 1024).toFixed(1)} MB`),
    );
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
      } else {
        reject(new Error('FileReader 返回非字符串结果'));
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error('FileReader 失败'));
    reader.readAsDataURL(file);
  });
}
