/**
 * 文件树 + 内容查看器。
 * - 左:/files 列表(点选);右:文件内容。
 * - 登录 + editable 时:可编辑 textarea + 保存(PUT)。
 */
import * as React from 'react';
import { File, FileCode2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { ApiError } from '@/api/client';
import { useFileContent, useScriptFiles, useWriteFile } from '@/api/hooks';
import { useAuth } from '@/auth/AuthProvider';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { ErrorState } from '@/components/States';

export function FileBrowser({ slug }: { slug: string }) {
  const { data, isLoading, isError, refetch } = useScriptFiles(slug);
  const [selected, setSelected] = React.useState<string | null>(null);

  // 默认选中第一个文件
  const files = data?.files ?? [];
  React.useEffect(() => {
    if (!selected && files.length > 0) {
      setSelected(files[0]!.path);
    }
  }, [files, selected]);

  if (isLoading) {
    return <Skeleton className="h-64 w-full rounded-lg" />;
  }
  if (isError) {
    return <ErrorState title="文件列表加载失败" onRetry={() => void refetch()} />;
  }
  if (files.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">该脚本没有文件。</p>;
  }

  const selectedItem = files.find((f) => f.path === selected) ?? null;

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(180px,240px)_1fr]">
      {/* 文件树 */}
      <div className="rounded-lg border bg-card/50 p-2">
        <ul className="space-y-0.5">
          {files.map((f) => {
            const active = f.path === selected;
            return (
              <li key={f.path}>
                <button
                  type="button"
                  onClick={() => setSelected(f.path)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                    active ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
                  )}
                  title={f.path}
                >
                  {f.editable ? (
                    <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <File className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate font-mono text-xs">{f.path}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* 内容 */}
      <div className="min-w-0">
        {selected && selectedItem ? (
          <FileViewer slug={slug} path={selected} editable={selectedItem.editable} size={selectedItem.size} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">选择左侧文件查看内容。</p>
        )}
      </div>
    </div>
  );
}

function FileViewer({
  slug,
  path,
  editable,
  size,
}: {
  slug: string;
  path: string;
  editable: boolean;
  size: number;
}) {
  const { user } = useAuth();
  const { data, isLoading, isError, refetch } = useFileContent(slug, path);
  const writeFile = useWriteFile(slug);

  const [draft, setDraft] = React.useState<string | null>(null);

  // 切换文件 / 重新加载时重置草稿
  React.useEffect(() => {
    setDraft(null);
  }, [path, data?.content]);

  const canEdit = !!user && editable;
  const content = data?.content ?? '';
  const value = draft ?? content;
  const dirty = draft !== null && draft !== content;

  const handleSave = async () => {
    if (draft === null) return;
    try {
      await writeFile.mutateAsync({ path, content: draft });
      toast.success(`已保存 ${path}`);
      setDraft(null);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        toast.error('请先登录');
      } else if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('保存失败');
      }
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs text-muted-foreground">{path}</span>
          <Badge variant="outline" className="shrink-0 text-[10px] font-normal">
            {formatBytes(size)}
          </Badge>
          {!editable && (
            <Badge variant="secondary" className="shrink-0 text-[10px] font-normal">
              只读
            </Badge>
          )}
        </div>
        {canEdit && (
          <Button size="sm" onClick={handleSave} disabled={!dirty || writeFile.isPending}>
            <Save />
            {writeFile.isPending ? '保存中…' : '保存'}
          </Button>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-72 w-full rounded-lg" />
      ) : isError ? (
        <ErrorState title="文件内容加载失败" onRetry={() => void refetch()} />
      ) : canEdit ? (
        <Textarea
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          className="h-[28rem] resize-y font-mono text-xs leading-relaxed"
        />
      ) : (
        <pre className="max-h-[28rem] overflow-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
          <code>{content}</code>
        </pre>
      )}
    </div>
  );
}
