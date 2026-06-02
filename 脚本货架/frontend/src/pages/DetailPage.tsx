import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Download, ExternalLink, ImportIcon, Pencil, UserRound } from 'lucide-react';

import { api, ApiError } from '@/api/client';
import { useScript, downloadBundle, qk } from '@/api/hooks';
import { bundleAbsoluteUrl, managerImportUrl } from '@/api/urls';
import type { FileContentResponse, FieldSummary } from '@/api/types';
import { useAuth } from '@/auth/AuthProvider';
import { formatBytes, formatRelative } from '@/lib/format';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ScriptIcon } from '@/components/ScriptIcon';
import { CopyButton } from '@/components/CopyButton';
import { FileBrowser } from '@/components/FileBrowser';
import { MarkdownView } from '@/components/MarkdownView';
import { TagEditor } from '@/components/TagEditor';
import { DeleteScriptButton } from '@/components/DeleteScriptButton';
import { LoadingState, ErrorState } from '@/components/States';

export function DetailPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const { data: script, isLoading, isError, error, refetch } = useScript(slug);
  const { user } = useAuth();

  if (isLoading) {
    return <LoadingState label="加载脚本详情…" />;
  }
  if (isError || !script) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorState
          title={notFound ? '脚本不存在' : '加载失败'}
          message={notFound ? `没有找到 slug 为 ${slug} 的脚本。` : error instanceof Error ? error.message : undefined}
          onRetry={notFound ? undefined : () => void refetch()}
        />
      </div>
    );
  }

  const bundleUrl = bundleAbsoluteUrl(script.slug);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-6">
        <BackLink />

        {/* 头部 */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <ScriptIcon slug={script.slug} hasIcon={script.has_icon} size={72} className="rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">{script.name}</h1>
              <Badge variant="secondary" className="font-mono">
                v{script.version}
              </Badge>
            </div>
            <p className="font-mono text-xs text-muted-foreground">{script.slug}</p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {script.author && (
                <span className="flex items-center gap-1">
                  <UserRound className="h-3.5 w-3.5" />
                  {script.author}
                </span>
              )}
              {script.homepage && (
                <a
                  href={script.homepage}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-primary hover:underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  主页
                </a>
              )}
              <span>更新于 {formatRelative(script.updated_at)}</span>
              <span className="tabular-nums">{script.download_count} 次下载</span>
            </div>

            {/* 标签 */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {script.tags.map((t) => (
                <Badge key={t} variant="outline" className="font-normal">
                  {t}
                </Badge>
              ))}
              {user && (
                <TagEditor
                  slug={script.slug}
                  tags={script.tags}
                  trigger={
                    <Button variant="ghost" size="sm" className="h-6 gap-1 px-2 text-xs text-muted-foreground">
                      <Pencil className="h-3 w-3" />
                      编辑标签
                    </Button>
                  }
                />
              )}
            </div>
          </div>
        </div>

        {/* 描述 */}
        {script.description && <p className="text-sm leading-relaxed text-foreground/90">{script.description}</p>}

        {/* 主操作按钮 */}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => downloadBundle(script.slug)}>
            <Download />
            下载 zip
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="secondary" asChild>
                <a href={managerImportUrl(script.slug)} target="_blank" rel="noreferrer">
                  <ImportIcon />
                  导入到管家
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent>在签到管家中打开并导入此脚本</TooltipContent>
          </Tooltip>

          <CopyButton
            variant="outline"
            value={bundleUrl}
            label="复制 bundle 链接"
            toastMessage="已复制 bundle.zip 链接"
          />

          {user && <DeleteScriptButton slug={script.slug} name={script.name} />}
        </div>

        {/* 配置字段表 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">配置字段</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldsTable fields={script.fields_summary} />
          </CardContent>
        </Card>

        {/* README */}
        <ReadmeSection slug={script.slug} />

        {/* 文件树 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              文件{' '}
              <span className="font-normal text-muted-foreground">
                ({script.file_count} 个 · {formatBytes(script.size_bytes)})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <FileBrowser slug={script.slug} />
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}

function BackLink() {
  return (
    <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" />
      返回画廊
    </Link>
  );
}

function FieldsTable({ fields }: { fields: FieldSummary[] }) {
  if (fields.length === 0) {
    return <p className="text-sm text-muted-foreground">该脚本无需配置字段。</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>键 (key)</TableHead>
          <TableHead>标签</TableHead>
          <TableHead>类型</TableHead>
          <TableHead className="text-center">必填</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {fields.map((f) => (
          <TableRow key={f.key}>
            <TableCell className="font-mono text-xs">{f.key}</TableCell>
            <TableCell>{f.label}</TableCell>
            <TableCell>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {f.type}
              </Badge>
            </TableCell>
            <TableCell className="text-center">
              {f.required ? (
                <Badge variant="default" className="text-[10px]">
                  必填
                </Badge>
              ) : (
                <span className="text-xs text-muted-foreground">可选</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** README:尝试取 files/README.md,404 / 空则整块隐藏。 */
function ReadmeSection({ slug }: { slug: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: qk.fileContent(slug, 'README.md'),
    queryFn: async () => {
      try {
        return await api.get<FileContentResponse>(`/api/scripts/${encodeURIComponent(slug)}/files/README.md`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    retry: false,
  });

  // 加载中不抢占空间;无 README / 出错则隐藏
  if (isLoading || isError || !data || !data.content.trim()) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">README</CardTitle>
      </CardHeader>
      <CardContent>
        <MarkdownView source={data.content} />
      </CardContent>
    </Card>
  );
}
