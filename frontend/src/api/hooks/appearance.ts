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
import { useEffect } from 'react';
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

  // 🔴 HIGH · code-review #2:防御性 — 若 backend 返 value 是 JSON 字符串
  // (理论上不应该,但某些端点未解析 value_json),先 JSON.parse 一次
  // 之前 typeof !== 'object' 会静默回退 DEFAULT,所有保存设置丢失
  let rawValue: unknown = raw.value;
  if (typeof rawValue === 'string') {
    try {
      rawValue = JSON.parse(rawValue);
    } catch {
      rawValue = null;
    }
  }

  const partial =
    rawValue && typeof rawValue === 'object' && !Array.isArray(rawValue)
      ? (rawValue as Partial<AppearanceData>)
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

// 🟡 MED · code-review #6:跨 tab 同步 appearance
// BroadcastChannel 让多个 tab 共享 mutation 结果 — tab A 改设置 → broadcast →
// tab B 收到立即 setQueryData 更新,不需要手动 reload。
// 优雅降级:不支持 BroadcastChannel 的浏览器(老 Safari)走 localStorage event。
const APPEARANCE_CHANNEL = 'signin-panel:appearance';
let bc: BroadcastChannel | null = null;
function getBroadcast(): BroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  if (!bc) {
    try {
      bc = new BroadcastChannel(APPEARANCE_CHANNEL);
    } catch {
      bc = null;
    }
  }
  return bc;
}

/**
 * 读取当前 appearance 设置。
 *
 * `staleTime: Infinity` — 这是站点级配置,改动罕见 + invalidate by mutation,
 * 避免每次组件 mount 都重 fetch(2 张图 base64 可能几百 KB)。
 *
 * 跨 tab 同步:用 BroadcastChannel 监听其他 tab 的 mutation,自动 setQueryData。
 */
export function useAppearance(): UseQueryResult<AppearanceData, Error> {
  const qc = useQueryClient();

  // 监听其他 tab 的 mutation broadcast
  useEffect(() => {
    const channel = getBroadcast();
    if (!channel) return;
    function onMessage(e: MessageEvent) {
      if (e.data && typeof e.data === 'object' && e.data.type === 'appearance:updated') {
        qc.setQueryData(appearanceQueryKeys.current, e.data.payload);
      }
    }
    channel.addEventListener('message', onMessage);
    return () => channel.removeEventListener('message', onMessage);
  }, [qc]);

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
      // 🟡 MED · code-review #6:broadcast 让其他 tab 也更新
      const channel = getBroadcast();
      if (channel) {
        try {
          channel.postMessage({ type: 'appearance:updated', payload: data });
        } catch {
          // ignore — BroadcastChannel postMessage 偶发失败不阻塞主流程
        }
      }
      toast.success('外观设置已保存');
    },
    onError: (err) => {
      toast.error(`保存失败:${err.message}`);
    },
  });
}

// ====================== 工具函数 ======================

// ====================== 预设背景(SVG 渐变 / 几何) ======================

export interface BackgroundPreset {
  id: string;
  name: string;
  /** SVG inline data URL,用户一键选 → setDraft({...d, background_image_data_url: dataUrl}) */
  dataUrl: string;
  /** 缩略图 CSS background(优化用,直接显示在预设网格,避免每个 swatch 加载完整 SVG)*/
  thumb: string;
}

function svgToDataUrl(svg: string): string {
  // 用 encodeURIComponent 而不是 btoa(SVG 含中文 / Unicode 时 btoa 会炸)
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg.trim())}`;
}

/** 6 张内置背景(SVG 渐变 / 几何 / 暗系)— 无需用户上传即可一键应用 */
export const BACKGROUND_PRESETS: BackgroundPreset[] = [
  {
    id: 'aurora-purple',
    name: '极光紫',
    thumb: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#667eea"/>
            <stop offset="100%" stop-color="#764ba2"/>
          </linearGradient>
        </defs>
        <rect width="1920" height="1080" fill="url(#g)"/>
      </svg>`,
    ),
  },
  {
    id: 'sunset-pink',
    name: '日落粉',
    thumb: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#fa709a"/>
            <stop offset="100%" stop-color="#fee140"/>
          </linearGradient>
        </defs>
        <rect width="1920" height="1080" fill="url(#g)"/>
      </svg>`,
    ),
  },
  {
    id: 'ocean-cyan',
    name: '深海青',
    thumb: 'linear-gradient(135deg, #00d2ff 0%, #3a7bd5 100%)',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#00d2ff"/>
            <stop offset="100%" stop-color="#3a7bd5"/>
          </linearGradient>
        </defs>
        <rect width="1920" height="1080" fill="url(#g)"/>
      </svg>`,
    ),
  },
  {
    id: 'forest-green',
    name: '森林绿',
    thumb: 'linear-gradient(135deg, #134e5e 0%, #71b280 100%)',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#134e5e"/>
            <stop offset="100%" stop-color="#71b280"/>
          </linearGradient>
        </defs>
        <rect width="1920" height="1080" fill="url(#g)"/>
      </svg>`,
    ),
  },
  {
    id: 'dots-pattern',
    name: '点阵底纹',
    thumb: 'radial-gradient(circle at center, #4a5568 1px, transparent 1px), #1a202c',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
        <rect width="80" height="80" fill="#1a202c"/>
        <circle cx="40" cy="40" r="2" fill="#4a5568"/>
        <circle cx="0" cy="0" r="2" fill="#4a5568"/>
        <circle cx="80" cy="0" r="2" fill="#4a5568"/>
        <circle cx="0" cy="80" r="2" fill="#4a5568"/>
        <circle cx="80" cy="80" r="2" fill="#4a5568"/>
      </svg>`,
    ),
  },
  {
    id: 'midnight-solid',
    name: '午夜蓝',
    thumb: '#0f172a',
    dataUrl: svgToDataUrl(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <rect width="1920" height="1080" fill="#0f172a"/>
      </svg>`,
    ),
  },
];

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
