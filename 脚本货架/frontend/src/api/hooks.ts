/**
 * React Query hooks — 脚本读写 + 文件读写。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import { bundlePath } from './urls';
import type {
  FileContentResponse,
  FileListResponse,
  MessageResponse,
  ScriptDetail,
  ScriptListItem,
  UploadResponse,
} from './types';

export const qk = {
  scripts: ['scripts'] as const,
  script: (slug: string) => ['scripts', slug] as const,
  files: (slug: string) => ['scripts', slug, 'files'] as const,
  fileContent: (slug: string, path: string) => ['scripts', slug, 'file', path] as const,
};

// ===== 读 =====
export function useScripts() {
  return useQuery({
    queryKey: qk.scripts,
    queryFn: () => api.get<ScriptListItem[]>('/api/scripts'),
  });
}

export function useScript(slug: string) {
  return useQuery({
    queryKey: qk.script(slug),
    queryFn: () => api.get<ScriptDetail>(`/api/scripts/${encodeURIComponent(slug)}`),
    enabled: !!slug,
  });
}

export function useScriptFiles(slug: string) {
  return useQuery({
    queryKey: qk.files(slug),
    queryFn: () => api.get<FileListResponse>(`/api/scripts/${encodeURIComponent(slug)}/files`),
    enabled: !!slug,
  });
}

export function useFileContent(slug: string, path: string | null) {
  return useQuery({
    queryKey: qk.fileContent(slug, path ?? ''),
    queryFn: () =>
      api.get<FileContentResponse>(
        `/api/scripts/${encodeURIComponent(slug)}/files/${path!.split('/').map(encodeURIComponent).join('/')}`,
      ),
    enabled: !!slug && !!path,
  });
}

// ===== 写(需登录) =====
export function useUploadScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, force }: { file: File; force: boolean }) =>
      api.uploadFile<UploadResponse>(`/api/scripts/upload?force=${force}`, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.scripts });
    },
  });
}

export function useUpdateTags(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tags: string[]) =>
      api.patch<ScriptDetail>(`/api/scripts/${encodeURIComponent(slug)}`, { tags }),
    onSuccess: (detail) => {
      qc.setQueryData(qk.script(slug), detail);
      void qc.invalidateQueries({ queryKey: qk.scripts });
    },
  });
}

/** 更新分类:传分类名设置,传 "" 清为未分类(后端 PATCH {category})。 */
export function useUpdateCategory(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (category: string) =>
      api.patch<ScriptDetail>(`/api/scripts/${encodeURIComponent(slug)}`, { category }),
    onSuccess: (detail) => {
      qc.setQueryData(qk.script(slug), detail);
      void qc.invalidateQueries({ queryKey: qk.scripts });
    },
  });
}

export function useWriteFile(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      api.put<ScriptDetail>(
        `/api/scripts/${encodeURIComponent(slug)}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
        { content },
      ),
    onSuccess: (detail, { path }) => {
      qc.setQueryData(qk.script(slug), detail);
      void qc.invalidateQueries({ queryKey: qk.fileContent(slug, path) });
      void qc.invalidateQueries({ queryKey: qk.files(slug) });
    },
  });
}

/** 修改密码:旧密码错后端返 401(ApiError.isUnauthorized),新密码 < 6 位返 422。 */
export function useChangePassword() {
  return useMutation({
    mutationFn: ({ oldPassword, newPassword }: { oldPassword: string; newPassword: string }) =>
      api.post<MessageResponse>('/api/auth/change-password', {
        old_password: oldPassword,
        new_password: newPassword,
      }),
  });
}

export function useDeleteScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.del<void>(`/api/scripts/${encodeURIComponent(slug)}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.scripts });
    },
  });
}

/** 触发浏览器下载 bundle.zip(用隐藏 a 标签,带 cookie 同源)。 */
export function downloadBundle(slug: string): void {
  const a = document.createElement('a');
  a.href = bundlePath(slug);
  a.download = `${slug}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
