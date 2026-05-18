/**
 * <ScriptFileList> — 脚本文件 flat 列表(MVP-5 概览 Tab 用)
 *
 * 设计契约:`进度/设计/Web脚本编辑器.md` § 3.1。
 *
 * 列每个文件:
 *   icon(扩展名) | 文件名 | size | mtime relative | [👁 查看] [✏️ 编辑]
 *
 * 折叠规则:
 *   - `.backups/` 目录默认隐藏("显示备份"复选框可展开)
 *   - 不可编辑(editable: false)文件 → 编辑按钮 disabled + tooltip
 *
 * 不做(MVP-5):
 *   - 嵌套树折叠(脚本目录通常 < 10 文件,扁平就好)
 *   - 拖拽排序 / 删除单文件
 */
import { useMemo, useState } from 'react';
import {
  Code2,
  Eye,
  FileBox,
  FileCode2,
  FileImage,
  FileJson,
  FileText,
  FolderArchive,
  Pencil,
  RefreshCw,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import EmptyState from '@/components/common/EmptyState';

import { useScriptFiles, type ScriptFileItem } from '@/api/hooks/useScriptFiles';
import { formatBytes, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

interface ScriptFileListProps {
  slug: string;
  /** 点击查看/编辑回调,由父组件渲染 FileEditDialog */
  onView?: (file: ScriptFileItem) => void;
  onEdit?: (file: ScriptFileItem) => void;
}

function iconForPath(path: string) {
  const lower = path.toLowerCase();
  if (lower.endsWith('.py')) return FileCode2;
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return FileText;
  if (lower.endsWith('.json')) return FileJson;
  if (lower.endsWith('.md') || lower.endsWith('.txt')) return FileText;
  if (lower.endsWith('.svg') || lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.webp')) {
    return FileImage;
  }
  if (lower.endsWith('.zip') || lower.endsWith('.tar') || lower.endsWith('.gz')) {
    return FolderArchive;
  }
  return FileBox;
}

function colorClassForPath(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith('.py')) return 'text-chart-2';
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'text-chart-4';
  if (lower.endsWith('.json')) return 'text-chart-3';
  if (lower.endsWith('.md')) return 'text-chart-1';
  if (lower.endsWith('.svg') || lower.endsWith('.png')) return 'text-chart-5';
  return 'text-muted-foreground/70';
}

export function ScriptFileList({ slug, onView, onEdit }: ScriptFileListProps) {
  const { data: files, isLoading, isError, error, refetch, isFetching } = useScriptFiles(slug);
  const [showBackups, setShowBackups] = useState(false);

  const visibleFiles = useMemo(() => {
    if (!files) return [];
    return files.filter((f) => {
      if (showBackups) return true;
      return !f.path.startsWith('.backups/') && !f.path.includes('/.backups/');
    });
  }, [files, showBackups]);

  const backupCount = useMemo(() => {
    if (!files) return 0;
    return files.filter(
      (f) => f.path.startsWith('.backups/') || f.path.includes('/.backups/'),
    ).length;
  }, [files]);

  return (
    <Card className="p-0">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Code2 className="size-4 text-muted-foreground" strokeWidth={1.75} />
          <h3 className="text-sm font-semibold text-foreground">脚本文件</h3>
          {files && files.length > 0 ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              ({visibleFiles.length}{backupCount > 0 ? `/${files.length}` : ''})
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {backupCount > 0 ? (
            <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
              <Checkbox
                checked={showBackups}
                onCheckedChange={(v) => setShowBackups(!!v)}
                className="size-3.5"
              />
              显示备份 ({backupCount})
            </label>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="刷新文件列表"
          >
            <RefreshCw
              className={cn('size-3.5', isFetching && 'animate-spin')}
              strokeWidth={1.75}
            />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2 p-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : isError ? (
        <div className="px-4 py-6 text-center">
          <p className="text-sm text-danger">无法加载文件列表</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {(error as Error)?.message || '后端未实现 GET /scripts/{slug}/files'}
          </p>
        </div>
      ) : visibleFiles.length === 0 ? (
        <EmptyState
          icon={FileBox}
          title="目录为空"
          description="磁盘上还没有任何脚本文件"
          className="py-8"
        />
      ) : (
        <TooltipProvider>
          <ul className="divide-y divide-border/70">
            {visibleFiles.map((f) => {
              const Icon = iconForPath(f.path);
              const colorCls = colorClassForPath(f.path);
              return (
                <li
                  key={f.path}
                  className="flex items-center gap-3 px-4 py-2 transition-colors hover:bg-muted/30"
                >
                  <Icon
                    className={cn('size-4 shrink-0', colorCls)}
                    strokeWidth={1.75}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-foreground">
                      {f.path}
                    </p>
                  </div>
                  <span className="hidden shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground sm:inline">
                    {formatBytes(f.size)}
                  </span>
                  <span
                    className="hidden w-24 shrink-0 text-right text-[11px] text-muted-foreground md:inline"
                    title={f.mtime}
                  >
                    {formatRelative(f.mtime)}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          onClick={() => onView?.(f)}
                          aria-label="查看文件"
                        >
                          <Eye className="size-3.5" strokeWidth={1.75} />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        查看
                      </TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => onEdit?.(f)}
                            disabled={!f.editable}
                            aria-label="编辑文件"
                          >
                            <Pencil className="size-3.5" strokeWidth={1.75} />
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        {f.editable
                          ? '编辑(Ctrl+S 保存)'
                          : '不可编辑(二进制 / 备份 / 超大)'}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </li>
              );
            })}
          </ul>
        </TooltipProvider>
      )}
    </Card>
  );
}

export default ScriptFileList;
