/**
 * <FileEditDialog> — 单文件在线编辑 / 查看(MVP-5 次流程)
 *
 * 设计契约:`进度/设计/Web脚本编辑器.md` § 3.3。
 *
 * 模式:
 *   - mode='edit':可改 + 保存(自动 dry-run)+ Ctrl+S
 *   - mode='view':只读,不显示保存按钮
 *
 * 关键 UX:
 *   - CodeMirror 通过 React.lazy 加载,主 bundle 不带
 *   - Ctrl+S = 保存
 *   - 关闭前若有 unsaved changes → confirm
 *   - 保存中显示 spinner "正在 dry-run..."(后端 30 秒超时)
 *   - 保存失败(dry-run 没过)→ 红色 inline 错误区,Dialog 不关
 *   - 文件大小 > 256 KB → 显示警告,保存按钮 disabled
 */
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileCode2,
  Loader2,
  Save,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';

import {
  useScriptFile,
  useScriptFileSave,
  type ScriptFileItem,
} from '@/api/hooks/useScriptFiles';
import { formatBytes, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

import { inferLanguageFromPath } from './fileLanguage';

// React.lazy → Vite 自动拆 chunk
const CodeMirrorLazyComp = lazy(() => import('./CodeMirrorLazy'));

const MAX_FILE_BYTES = 256 * 1024; // 256 KB,与后端约束一致

export interface FileEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slug: string;
  /** 要打开的文件相对路径,如 'main.py' / 'manifest.yaml' */
  path: string;
  /** 列表项里已有的元信息(size / mtime 用来 header 显示,避免再请求) */
  meta?: ScriptFileItem | null;
  mode?: 'edit' | 'view';
}

export function FileEditDialog({
  open,
  onOpenChange,
  slug,
  path,
  meta,
  mode = 'edit',
}: FileEditDialogProps) {
  const { data: loadedContent, isLoading, isError, error } = useScriptFile(slug, path, open);
  const saveMutation = useScriptFileSave();

  const [draft, setDraft] = useState<string>('');
  const [autoDryRun, setAutoDryRun] = useState<boolean>(true);
  const [saveError, setSaveError] = useState<{ msg: string; detail?: unknown } | null>(null);

  const language = useMemo(() => inferLanguageFromPath(path), [path]);
  const readOnly = mode === 'view';

  // 文件加载后初始化 draft
  useEffect(() => {
    if (loadedContent !== undefined) {
      setDraft(loadedContent);
    }
  }, [loadedContent]);

  // Dialog 关闭时重置
  useEffect(() => {
    if (!open) {
      setDraft('');
      setSaveError(null);
      saveMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const isDirty = !readOnly && loadedContent !== undefined && draft !== loadedContent;
  const tooBig = draft.length > MAX_FILE_BYTES;
  const isSaving = saveMutation.isPending;

  const handleSave = useCallback(async () => {
    if (readOnly || isSaving || tooBig) return;
    setSaveError(null);
    try {
      await saveMutation.mutateAsync({
        slug,
        path,
        content: draft,
        skip_dry_run: !autoDryRun,
      });
      // 成功 → 关闭(全局 toast 已经响)
      onOpenChange(false);
    } catch (err) {
      const e = err as Error & { detail?: unknown };
      setSaveError({ msg: e.message || '保存失败', detail: e.detail });
    }
  }, [autoDryRun, draft, isSaving, onOpenChange, path, readOnly, saveMutation, slug, tooBig]);

  const handleClose = useCallback(
    (next: boolean) => {
      if (!next && isDirty && !isSaving) {
        const ok = window.confirm('有未保存的修改,确定放弃?');
        if (!ok) return;
      }
      onOpenChange(next);
    },
    [isDirty, isSaving, onOpenChange],
  );

  const dryRunStderr = useMemo<string | null>(() => {
    if (!saveError?.detail || typeof saveError.detail !== 'object') return null;
    const d = saveError.detail as Record<string, unknown>;
    if (d.dry_run && typeof d.dry_run === 'object') {
      const dr = d.dry_run as { stderr_excerpt?: string; stdout_excerpt?: string };
      return dr.stderr_excerpt || dr.stdout_excerpt || null;
    }
    if (typeof d.stderr_excerpt === 'string') return d.stderr_excerpt;
    return null;
  }, [saveError]);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="flex max-h-[90vh] max-w-3xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="size-4 text-primary" strokeWidth={1.75} />
            {readOnly ? '查看' : '编辑'} <code className="font-mono text-sm">{path}</code>
          </DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="flex items-center gap-1">
              <span className="text-muted-foreground/60">大小:</span>
              <span
                className={cn(
                  'tabular-nums',
                  tooBig && 'font-semibold text-danger',
                )}
              >
                {formatBytes(draft.length || meta?.size || 0)} / {formatBytes(MAX_FILE_BYTES)}
              </span>
            </span>
            {meta?.mtime ? (
              <span className="flex items-center gap-1">
                <Clock className="size-3" strokeWidth={1.75} />
                <span className="text-muted-foreground/60">改于</span>
                <span title={meta.mtime}>{formatRelative(meta.mtime)}</span>
              </span>
            ) : null}
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
              {language}
            </span>
          </DialogDescription>
        </DialogHeader>

        {/* 编辑器主区 */}
        <div className="flex-1 overflow-hidden border-b border-border bg-muted/20 px-1 py-1">
          {isLoading ? (
            <div className="flex h-full min-h-[320px] items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
                正在加载文件...
              </div>
            </div>
          ) : isError ? (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 px-6 text-center">
              <AlertCircle className="size-8 text-danger" strokeWidth={1.5} />
              <p className="text-sm font-medium text-foreground">无法加载文件</p>
              <p className="max-w-md text-xs text-muted-foreground">
                {(error as Error)?.message || '后端拒绝读取(可能是二进制或路径不合规)'}
              </p>
            </div>
          ) : (
            <Suspense
              fallback={
                <div className="space-y-2 p-4">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-4/5" />
                </div>
              }
            >
              <CodeMirrorLazyComp
                value={draft}
                onChange={readOnly ? undefined : setDraft}
                language={language}
                readOnly={readOnly}
                onSave={readOnly ? undefined : handleSave}
              />
            </Suspense>
          )}
        </div>

        {/* 错误区(dry-run 失败) */}
        {saveError ? (
          <div className="border-b border-danger/30 bg-danger/5 px-6 py-3">
            <div className="flex items-start gap-2">
              <AlertCircle
                className="mt-0.5 size-4 shrink-0 text-danger"
                strokeWidth={1.75}
              />
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-sm font-medium text-foreground">
                  保存失败:{saveError.msg}
                </p>
                {dryRunStderr ? (
                  <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-background/50 p-2 font-mono text-[10px] text-muted-foreground">
                    {dryRunStderr}
                  </pre>
                ) : null}
                <p className="text-[11px] text-muted-foreground">
                  请改正后再次保存。Dialog 不会自动关闭。
                </p>
              </div>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setSaveError(null)}
                aria-label="关闭错误提示"
              >
                <X className="size-4" strokeWidth={1.75} />
              </button>
            </div>
          </div>
        ) : null}

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
          {readOnly ? (
            <div className="flex-1" />
          ) : (
            <label className="flex cursor-pointer items-center gap-2 text-xs">
              <Checkbox
                checked={autoDryRun}
                onCheckedChange={(v) => setAutoDryRun(!!v)}
                disabled={isSaving}
              />
              <span>
                保存前自动 dry-run
                <span className="ml-1 text-muted-foreground/70">(推荐,30 秒超时)</span>
              </span>
            </label>
          )}
          <div className="flex items-center gap-2">
            {isDirty ? (
              <span className="text-[11px] text-warning">● 未保存</span>
            ) : !readOnly && loadedContent !== undefined ? (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <CheckCircle2 className="size-3" strokeWidth={1.75} />
                无变化
              </span>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleClose(false)}
              disabled={isSaving}
            >
              {readOnly ? '关闭' : '取消'}
            </Button>
            {!readOnly ? (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={!isDirty || isSaving || tooBig || isLoading}
                title={tooBig ? '文件超过 256 KB 上限' : 'Ctrl+S 等同'}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
                    {autoDryRun ? '正在 dry-run...' : '保存中...'}
                  </>
                ) : (
                  <>
                    <Save className="mr-1.5 size-4" strokeWidth={1.75} />
                    保存
                  </>
                )}
              </Button>
            ) : null}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default FileEditDialog;
