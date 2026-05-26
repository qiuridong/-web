/**
 * <UploadScriptDialog> — 上传脚本目录 / zip(MVP-5 主流程)
 *
 * 设计契约:`进度/设计/Web脚本编辑器.md` § 3.2(上传 Dialog wireframe)+ § 3.4(UX)。
 *
 * 三态:
 *   - 选择文件态:Drop Zone + 表单(slug / force / dry_run)
 *   - 上传中态:Progress Bar + spinner + "取消"
 *   - 完成态:成功面板 / 失败面板(失败可"重试"回退到选择态)
 *
 * 与后端契约:
 *   - 单 .zip → POST application/zip
 *   - 多文件 / 文件夹 → POST multipart/form-data(每个 part 用 webkitRelativePath 作 filename)
 *
 * 错误处理:
 *   - 422 / 409 / 413 等业务错误 → 红色错误面板 + 错误文本(从 detail / message 抽)
 *   - 不再 toast(避免局部错误 + 全局 toast 双 ping)
 *   - 网络层错误 → 同上面板,提示"检查后端是否运行"
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useDropzone } from 'react-dropzone';
import JSZip from 'jszip';
import yaml from 'js-yaml';
import { toast } from 'sonner';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Circle,
  Download,
  Files,
  FolderUp,
  Loader2,
  Package,
  Server,
  Upload as UploadIcon,
  X,
  XCircle,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';

import {
  useScriptUpload,
  type UploadError,
  type UploadResponse,
} from '@/api/hooks/useScriptUpload';
import { useNodes } from '@/api/hooks/nodes';
import { formatBytes } from '@/lib/format';
import {
  SCRIPT_REQUIRED_FILES,
  buildTemplateZip,
  downloadBlob,
} from '@/lib/script-template';
import { cn } from '@/lib/utils';

import { ScriptDevGuideSheet } from './ScriptDevGuideSheet';

// ============ 上传前的文件清单解析 ============

interface ManifestSummary {
  slug: string;
  name: string;
  version: string;
  fieldCount: number;
}

interface FileAnalysis {
  /** 每个 required file 的存在状态(present / missing) */
  checklist: Record<string, 'present' | 'missing'>;
  /** manifest.yaml 解析摘要,失败为 null */
  manifestSummary: ManifestSummary | null;
  /** yaml 解析错误(若有) */
  yamlError: string | null;
  /** 是否检测到 .py 主入口外的额外 .py 文件(纯展示,无校验意义) */
  extraPyCount: number;
}

/**
 * 解析上传的 zip 或文件夹,返回文件清单 + manifest 摘要。
 *
 * 处理两种来源:
 * - 单个 .zip 文件(用 jszip 解压解析)
 * - 多个 File(folder upload,用 webkitRelativePath)
 *
 * 对每个 RequiredFile,以 basename 在最浅深度的位置查找。
 */
async function analyzeUpload(files: File[]): Promise<FileAnalysis> {
  type Entry = { path: string; getText: () => Promise<string> };
  const entries: Entry[] = [];

  const single = files.length === 1 ? files[0] : undefined;
  if (single && single.name.toLowerCase().endsWith('.zip')) {
    const buf = await single.arrayBuffer();
    const zip = await JSZip.loadAsync(buf);
    for (const [name, entry] of Object.entries(zip.files)) {
      if (entry.dir) continue;
      entries.push({
        path: name,
        getText: () => entry.async('text'),
      });
    }
  } else {
    for (const f of files) {
      const path =
        (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
      entries.push({
        path,
        getText: () => f.text(),
      });
    }
  }

  // 找 basename 在最浅深度的 entry
  function findShallowest(basename: string): Entry | null {
    let best: Entry | null = null;
    let bestDepth = Number.POSITIVE_INFINITY;
    for (const e of entries) {
      const parts = e.path.split(/[/\\]/);
      const last = parts[parts.length - 1];
      if (last === basename) {
        const depth = parts.length - 1;
        if (depth < bestDepth) {
          bestDepth = depth;
          best = e;
        }
      }
    }
    return best;
  }

  const checklist: Record<string, 'present' | 'missing'> = {};
  for (const r of SCRIPT_REQUIRED_FILES) {
    checklist[r.filename] = findShallowest(r.filename) ? 'present' : 'missing';
  }

  let manifestSummary: ManifestSummary | null = null;
  let yamlError: string | null = null;
  const manifestEntry = findShallowest('manifest.yaml');
  if (manifestEntry) {
    try {
      const text = await manifestEntry.getText();
      const parsed = yaml.load(text) as Record<string, unknown> | null;
      if (parsed && typeof parsed === 'object') {
        manifestSummary = {
          slug: String(parsed.slug || ''),
          name: String(parsed.name || ''),
          version: String(parsed.version || ''),
          fieldCount: Array.isArray(parsed.fields) ? parsed.fields.length : 0,
        };
      } else {
        yamlError = 'manifest.yaml 顶层必须是 mapping(键值对)';
      }
    } catch (e) {
      yamlError = e instanceof Error ? e.message : String(e);
    }
  }

  const extraPyCount = entries.filter((e) => {
    const last = e.path.split(/[/\\]/).pop() ?? '';
    return last.toLowerCase().endsWith('.py') && last !== 'main.py';
  }).length;

  return { checklist, manifestSummary, yamlError, extraPyCount };
}

interface UploadScriptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Phase = 'idle' | 'uploading' | 'success' | 'error';

const SLUG_RE = /^[a-z][a-z0-9_-]{1,40}$/;

export function UploadScriptDialog({ open, onOpenChange }: UploadScriptDialogProps) {
  const navigate = useNavigate();
  const { upload, progress, isUploading, abort, reset } = useScriptUpload();

  const [files, setFiles] = useState<File[]>([]);
  const [slug, setSlug] = useState('');
  const [force, setForce] = useState(false);
  const [dryRun, setDryRun] = useState(true);

  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<unknown>(null);

  // 文件清单解析(拖入文件后立即跑)
  const [analysis, setAnalysis] = useState<FileAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  // 开发指南 Sheet
  const [guideOpen, setGuideOpen] = useState(false);

  // 下载模板 loading
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);

  // 同步到节点(可选,可多选)— MVP 仅 UI 提示,实际同步走按需 Pull
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([]);
  const { data: nodesData } = useNodes();
  const enabledNodes = useMemo(
    () => (nodesData?.items ?? []).filter((n) => n.enabled),
    [nodesData],
  );

  function toggleNodeId(id: number, checked: boolean) {
    setSelectedNodeIds((prev) =>
      checked ? [...prev, id] : prev.filter((x) => x !== id),
    );
  }

  // 客户端 slug 校验(留空也合法,后端会 fallback 到 manifest.yaml 里的 slug)
  const slugTrim = slug.trim();
  const slugError = useMemo(() => {
    if (!slugTrim) return null;
    if (!SLUG_RE.test(slugTrim)) {
      return '必须以小写字母开头,只含小写字母/数字/_/-,长度 2-41';
    }
    return null;
  }, [slugTrim]);

  // 拖拽 / 选文件 callback
  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length === 0) return;
    setFiles(accepted);
  }, []);

  const { getRootProps, getInputProps, isDragActive, open: openFilePicker } = useDropzone({
    onDrop,
    multiple: true,
    noClick: true, // 防止整个 zone 被点击触发(我们用专门按钮)
    noKeyboard: true,
  });

  // "选择文件夹"按钮 — react-dropzone 默认不传 webkitdirectory,
  // 我们自己造一个隐藏 input
  const onPickFolder = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    // webkitdirectory 是 Chrome/Edge/Safari 都支持的非标 API;TS lib.dom 已收录
    (input as HTMLInputElement & { webkitdirectory: boolean }).webkitdirectory = true;
    input.multiple = true;
    input.onchange = () => {
      if (input.files && input.files.length > 0) {
        setFiles(Array.from(input.files));
      }
    };
    input.click();
  }, []);

  const totalSize = useMemo(
    () => files.reduce((s, f) => s + f.size, 0),
    [files],
  );

  // files 变化 → 立即跑分析(异步)
  useEffect(() => {
    if (files.length === 0) {
      setAnalysis(null);
      setAnalyzeError(null);
      return;
    }
    let cancelled = false;
    setAnalyzing(true);
    setAnalyzeError(null);
    analyzeUpload(files)
      .then((res) => {
        if (!cancelled) setAnalysis(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setAnalysis(null);
          setAnalyzeError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setAnalyzing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [files]);

  // 校验:必填文件是否齐全
  const missingRequired = useMemo(() => {
    if (!analysis) return [];
    return SCRIPT_REQUIRED_FILES.filter(
      (f) => f.required && analysis.checklist[f.filename] !== 'present',
    );
  }, [analysis]);

  // 下载模板 zip
  const handleDownloadTemplate = useCallback(async () => {
    setDownloadingTemplate(true);
    try {
      const blob = await buildTemplateZip('my-script-template');
      downloadBlob(blob, 'my-script-template.zip');
    } catch (e) {
      // 极少失败,只 log
      // eslint-disable-next-line no-console
      console.error('下载模板失败', e);
    } finally {
      setDownloadingTemplate(false);
    }
  }, []);

  // 重置整个 Dialog 状态(关闭时调用)
  const resetAll = useCallback(() => {
    setFiles([]);
    setSlug('');
    setForce(false);
    setDryRun(true);
    setPhase('idle');
    setResult(null);
    setErrorMsg(null);
    setErrorDetail(null);
    setAnalysis(null);
    setAnalyzing(false);
    setAnalyzeError(null);
    setSelectedNodeIds([]);
    reset();
  }, [reset]);

  const handleClose = useCallback(
    (next: boolean) => {
      // 上传中关闭 → 主动 abort
      if (!next && isUploading) {
        abort();
      }
      if (!next) {
        // 延迟清理,避免动画期间内容闪烁
        setTimeout(resetAll, 220);
      }
      onOpenChange(next);
    },
    [abort, isUploading, onOpenChange, resetAll],
  );

  const startUpload = useCallback(async () => {
    if (files.length === 0 || slugError) return;
    setPhase('uploading');
    setErrorMsg(null);
    setErrorDetail(null);
    try {
      const resp = await upload(files, {
        slug: slugTrim || undefined,
        force,
        dry_run: dryRun,
      });
      setResult(resp);
      setPhase('success');
      // MVP-2 · 仅提示,不实际推送 — agent 在跑实例时自动 Pull 同步
      if (selectedNodeIds.length > 0) {
        const nodeNames = enabledNodes
          .filter((n) => selectedNodeIds.includes(n.id))
          .map((n) => n.slug)
          .join(' / ');
        toast.info(
          `已上传到主面板。选中的 ${selectedNodeIds.length} 个节点(${nodeNames})会在创建/跑实例时自动 Pull 同步脚本`,
          { duration: 8000 },
        );
      }
    } catch (err) {
      // 用户点取消触发 AbortError → 回到 idle,不显示错误
      if (err instanceof DOMException && err.name === 'AbortError') {
        setPhase('idle');
        return;
      }
      // 业务错误(UploadError)or 网络错误
      const e = err as UploadError | Error;
      setErrorMsg(e.message || '上传失败');
      setErrorDetail('detail' in e ? e.detail : null);
      setPhase('error');
    }
  }, [dryRun, files, force, slugError, slugTrim, upload]);

  const canSubmit =
    files.length > 0 &&
    !slugError &&
    !isUploading &&
    !analyzing &&
    missingRequired.length === 0 &&
    !analyzeError;

  return (
    <>
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-xl gap-0 p-0">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <UploadIcon className="size-4 text-primary" strokeWidth={1.75} />
            添加脚本
          </DialogTitle>
          <DialogDescription className="text-xs">
            把现成的脚本目录或 .zip 文件拖到下方,后端会自动校验 manifest.yaml + 入库。
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] overflow-y-auto p-6">
          {phase === 'success' && result ? (
            <SuccessPanel
              result={result}
              onJump={() => {
                handleClose(false);
                navigate(`/scripts/${result.slug}`);
              }}
              onCloseAndRefresh={() => handleClose(false)}
            />
          ) : phase === 'error' ? (
            <ErrorPanel
              message={errorMsg ?? '上传失败'}
              detail={errorDetail}
              onRetry={() => {
                setPhase('idle');
                setErrorMsg(null);
                setErrorDetail(null);
              }}
            />
          ) : (
            <>
              {/* 工具栏:下载模板 + 开发指南 */}
              <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
                <p className="mr-auto text-[11px] text-muted-foreground">
                  第一次写脚本?先下载模板项目,改改 manifest + main.py 即可
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 px-2 text-xs"
                  onClick={handleDownloadTemplate}
                  disabled={downloadingTemplate}
                >
                  {downloadingTemplate ? (
                    <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
                  ) : (
                    <Download className="size-3.5" strokeWidth={1.75} />
                  )}
                  下载模板项目
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 px-2 text-xs"
                  onClick={() => setGuideOpen(true)}
                >
                  <BookOpen className="size-3.5" strokeWidth={1.75} />
                  脚本开发指南
                </Button>
              </div>

              {/* 拖拽区 */}
              <div
                {...getRootProps()}
                className={cn(
                  'mb-4 flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors',
                  isDragActive
                    ? 'border-primary bg-primary/5'
                    : 'border-border bg-muted/20 hover:bg-muted/30',
                )}
              >
                <input {...getInputProps()} />
                <FolderUp
                  className={cn(
                    'size-10',
                    isDragActive ? 'text-primary' : 'text-muted-foreground/60',
                  )}
                  strokeWidth={1.5}
                />
                <div className="space-y-1">
                  <p className="text-sm font-medium text-foreground">
                    {isDragActive ? '松开以选择' : '拖一个文件夹或 .zip 文件到这里'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    或使用下方按钮选择
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onPickFolder();
                    }}
                    disabled={isUploading}
                  >
                    <FolderUp className="mr-1.5 size-3.5" strokeWidth={1.75} />
                    选择文件夹
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      openFilePicker();
                    }}
                    disabled={isUploading}
                  >
                    <Package className="mr-1.5 size-3.5" strokeWidth={1.75} />
                    选 .zip
                  </Button>
                </div>
              </div>

              {/* 文件清单分析(拖入后立即解析) */}
              {files.length > 0 ? (
                <FileChecklist
                  analysis={analysis}
                  analyzing={analyzing}
                  error={analyzeError}
                  missingRequired={missingRequired}
                />
              ) : null}

              {/* 文件预览 */}
              {files.length > 0 ? (
                <div className="mb-4 rounded-md border border-border bg-card/50 p-3">
                  <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <Files className="size-3.5" strokeWidth={1.75} />
                      即将上传 {files.length} 个文件,共 {formatBytes(totalSize)}
                    </span>
                    {!isUploading ? (
                      <button
                        type="button"
                        className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
                        onClick={() => setFiles([])}
                      >
                        <X className="size-3" strokeWidth={1.75} />
                        清空
                      </button>
                    ) : null}
                  </div>
                  <ul className="max-h-32 space-y-0.5 overflow-y-auto text-[11px]">
                    {files.slice(0, 30).map((f, i) => {
                      const rel =
                        (f as File & { webkitRelativePath?: string }).webkitRelativePath ||
                        f.name;
                      return (
                        <li key={`${rel}-${i}`} className="flex items-center justify-between gap-2 font-mono">
                          <span className="truncate text-muted-foreground">{rel}</span>
                          <span className="shrink-0 tabular-nums text-muted-foreground/70">
                            {formatBytes(f.size)}
                          </span>
                        </li>
                      );
                    })}
                    {files.length > 30 ? (
                      <li className="font-mono text-muted-foreground/60">
                        ... 还有 {files.length - 30} 个文件未展示
                      </li>
                    ) : null}
                  </ul>
                </div>
              ) : null}

              {/* 表单 */}
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="upload-slug" className="text-xs">
                    Slug(URL 标识,英文小写)
                  </Label>
                  <Input
                    id="upload-slug"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="留空 → 使用 manifest.yaml 里的 slug"
                    className={cn(
                      'h-9 font-mono text-sm',
                      slugError && 'border-danger focus-visible:ring-danger',
                    )}
                    disabled={isUploading}
                  />
                  {slugError ? (
                    <p className="text-[11px] text-danger">{slugError}</p>
                  ) : (
                    <p className="text-[11px] text-muted-foreground">
                      规则:小写字母开头,可含小写字母 / 数字 / _ / -,长度 2-41
                    </p>
                  )}
                </div>

                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    id="upload-dryrun"
                    checked={dryRun}
                    onCheckedChange={(v) => setDryRun(!!v)}
                    disabled={isUploading}
                  />
                  <span className="cursor-pointer">
                    上传前自动 dry-run(推荐)
                    <span className="ml-1 text-[11px] text-muted-foreground">
                      用 sandbox 跑一次,失败不入库
                    </span>
                  </span>
                </label>

                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    id="upload-force"
                    checked={force}
                    onCheckedChange={(v) => setForce(!!v)}
                    disabled={isUploading}
                  />
                  <span className="cursor-pointer">
                    slug 已存在则覆盖(force)
                    <span className="ml-1 text-[11px] text-muted-foreground">
                      旧文件会被替换,但 DB 实例配置保留
                    </span>
                  </span>
                </label>

                {/* 同步到节点(可选,可多选) — MVP 仅 UI 标记 */}
                <div className="space-y-1.5 rounded-md border border-border bg-muted/20 p-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Server className="size-3.5" strokeWidth={1.75} />
                    同步到节点(可选,可多选)
                  </div>
                  {enabledNodes.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">
                      暂无可用节点。可去 /nodes 创建,创建后此处自动出现。
                    </p>
                  ) : (
                    <ul className="space-y-1">
                      {enabledNodes.map((n) => (
                        <li
                          key={n.id}
                          className="flex items-center gap-2 text-xs"
                        >
                          <Checkbox
                            id={`upload-node-${n.id}`}
                            checked={selectedNodeIds.includes(n.id)}
                            onCheckedChange={(v) => toggleNodeId(n.id, !!v)}
                            disabled={isUploading}
                          />
                          <label
                            htmlFor={`upload-node-${n.id}`}
                            className="flex flex-1 cursor-pointer items-center gap-2"
                          >
                            <code className="font-mono text-foreground">
                              {n.slug}
                            </code>
                            {n.name ? (
                              <span className="text-muted-foreground">
                                · {n.name}
                              </span>
                            ) : null}
                            <span className="ml-auto flex items-center gap-1.5 text-[10px]">
                              {n.is_local ? (
                                <span className="rounded bg-primary/10 px-1 py-0.5 text-primary">
                                  本地
                                </span>
                              ) : n.online ? (
                                <span className="rounded bg-success/10 px-1 py-0.5 text-success">
                                  在线
                                </span>
                              ) : (
                                <span className="rounded bg-warning/10 px-1 py-0.5 text-warning">
                                  离线
                                </span>
                              )}
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-[10.5px] text-muted-foreground">
                    本次为预提示,不会立即推送。脚本会在 <strong>首次跑实例时</strong> 由 agent 自动 Pull 同步(MVP-2,按需,免维护)。
                  </p>
                </div>
              </div>

              {/* 上传中:进度条 */}
              {isUploading ? (
                <div className="mt-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
                      正在上传...
                    </span>
                    <span className="tabular-nums">{progress}%</span>
                  </div>
                  <Progress value={progress} className="h-2" />
                </div>
              ) : null}
            </>
          )}
        </div>

        {/* Footer 仅在 idle / uploading 显示;success/error 自带按钮 */}
        {phase !== 'success' && phase !== 'error' ? (
          <DialogFooter className="gap-2 border-t border-border px-6 py-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleClose(false)}
              disabled={false /* 取消随时可用 */}
            >
              {isUploading ? '取消上传' : '取消'}
            </Button>
            <Button
              size="sm"
              onClick={startUpload}
              disabled={!canSubmit}
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
                  上传中
                </>
              ) : (
                <>
                  <UploadIcon className="mr-1.5 size-4" strokeWidth={1.75} />
                  开始上传
                </>
              )}
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
    <ScriptDevGuideSheet open={guideOpen} onOpenChange={setGuideOpen} />
    </>
  );
}

// ============ 子面板 ============

function FileChecklist({
  analysis,
  analyzing,
  error,
  missingRequired,
}: {
  analysis: FileAnalysis | null;
  analyzing: boolean;
  error: string | null;
  missingRequired: { filename: string; hint: string }[];
}) {
  if (analyzing) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-md border border-border bg-card/50 px-3 py-2 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
        正在解析文件清单...
      </div>
    );
  }

  if (error) {
    return (
      <div className="mb-4 rounded-md border border-danger/30 bg-danger/10 p-3 text-xs">
        <p className="font-medium text-foreground">解析失败</p>
        <p className="mt-1 text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (!analysis) return null;

  const { checklist, manifestSummary, yamlError, extraPyCount } = analysis;

  return (
    <div className="mb-4 space-y-3 rounded-md border border-border bg-card/50 p-3">
      {/* 清单 */}
      <div>
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          文件清单({missingRequired.length === 0 ? '✅ 齐全' : `❌ 缺 ${missingRequired.length} 个必填`})
        </p>
        <ul className="space-y-1">
          {SCRIPT_REQUIRED_FILES.map((r) => {
            const present = checklist[r.filename] === 'present';
            const Icon = present
              ? CheckCircle2
              : r.required
                ? XCircle
                : Circle;
            const color = present
              ? 'text-success'
              : r.required
                ? 'text-danger'
                : 'text-muted-foreground/40';
            return (
              <li
                key={r.filename}
                className="flex items-start gap-2 text-[11.5px]"
              >
                <Icon className={cn('mt-0.5 size-3.5 shrink-0', color)} strokeWidth={1.75} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-1.5">
                    <code
                      className={cn(
                        'font-mono text-[11.5px]',
                        present
                          ? 'text-foreground'
                          : r.required
                            ? 'text-danger'
                            : 'text-muted-foreground/70',
                      )}
                    >
                      {r.filename}
                    </code>
                    <span className="text-[10.5px] text-muted-foreground/80">
                      {r.required ? '必填' : '可选'}
                    </span>
                  </div>
                  <p className="text-[10.5px] text-muted-foreground/80">
                    {r.hint}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
        {extraPyCount > 0 ? (
          <p className="mt-2 text-[10.5px] text-muted-foreground">
            另检测到 {extraPyCount} 个其他 .py 文件(模块拆分,无需操作)
          </p>
        ) : null}
      </div>

      {/* manifest 摘要 / yaml 错误 */}
      {manifestSummary ? (
        <div className="rounded-md border border-success/20 bg-success/5 px-2.5 py-2 text-[11px]">
          <p className="mb-1 font-semibold text-success">manifest.yaml 解析成功</p>
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-muted-foreground">
            <span>slug</span>
            <code className="font-mono text-foreground">{manifestSummary.slug || '(空)'}</code>
            <span>name</span>
            <span className="truncate text-foreground">{manifestSummary.name || '(空)'}</span>
            <span>version</span>
            <code className="font-mono text-foreground">{manifestSummary.version || '(空)'}</code>
            <span>fields</span>
            <span className="text-foreground">{manifestSummary.fieldCount} 个配置项</span>
          </div>
        </div>
      ) : yamlError ? (
        <div className="rounded-md border border-danger/30 bg-danger/10 px-2.5 py-2 text-[11px]">
          <p className="mb-1 font-semibold text-danger">manifest.yaml 解析失败</p>
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[10.5px] text-muted-foreground">
            {yamlError}
          </pre>
        </div>
      ) : null}

      {/* 必填提示 */}
      {missingRequired.length > 0 ? (
        <div className="rounded-md border border-danger/30 bg-danger/10 px-2.5 py-2 text-[11px]">
          <p className="font-semibold text-danger">
            缺 {missingRequired.length} 个必填文件,请先补齐再上传:
          </p>
          <ul className="mt-1 space-y-0.5">
            {missingRequired.map((f) => (
              <li key={f.filename} className="text-muted-foreground">
                <code className="font-mono text-foreground">{f.filename}</code> · {f.hint}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function SuccessPanel({
  result,
  onJump,
  onCloseAndRefresh,
}: {
  result: UploadResponse;
  onJump: () => void;
  onCloseAndRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-lg border border-success/30 bg-success/10 p-3">
        <CheckCircle2 className="size-6 shrink-0 text-success" strokeWidth={1.75} />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">上传成功</p>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {result.saved_path}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
          写入文件({result.files_written.length})
        </p>
        <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border bg-card/40 p-2 font-mono text-[11px]">
          {result.files_written.map((p) => (
            <li key={p} className="flex items-center gap-1.5">
              <CheckCircle2 className="size-3 shrink-0 text-success" strokeWidth={1.75} />
              <span className="truncate text-foreground">{p}</span>
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-muted-foreground">
          共 {formatBytes(result.total_bytes)}
        </p>
      </div>

      {result.dry_run ? (
        <div
          className={cn(
            'rounded-md border p-3 text-xs',
            result.dry_run.passed
              ? 'border-success/30 bg-success/5'
              : 'border-warning/30 bg-warning/5',
          )}
        >
          <p className="mb-1 font-medium">
            Dry-run:{' '}
            {result.dry_run.passed ? (
              <span className="text-success">通过</span>
            ) : (
              <span className="text-warning">未通过(exit={result.dry_run.exit_code})</span>
            )}
            <span className="ml-2 font-mono text-muted-foreground tabular-nums">
              {result.dry_run.duration_ms}ms
            </span>
          </p>
          {result.dry_run.stderr_excerpt ? (
            <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-background/50 p-2 font-mono text-[10px] text-muted-foreground">
              {result.dry_run.stderr_excerpt}
            </pre>
          ) : null}
        </div>
      ) : null}

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onCloseAndRefresh}>
          关闭并刷新列表
        </Button>
        <Button size="sm" onClick={onJump}>
          跳转到脚本详情
        </Button>
      </div>
    </div>
  );
}

function ErrorPanel({
  message,
  detail,
  onRetry,
}: {
  message: string;
  detail: unknown;
  onRetry: () => void;
}) {
  // 把 detail 里可能藏的 dry-run stderr / pydantic 校验列表抽出来
  const renderDetail = (): string | null => {
    if (!detail || typeof detail !== 'object') return null;
    const d = detail as Record<string, unknown>;
    // dry-run 错:detail = { dry_run: {...} }
    if (d.dry_run && typeof d.dry_run === 'object') {
      const dr = d.dry_run as { stderr_excerpt?: string; stdout_excerpt?: string };
      return dr.stderr_excerpt || dr.stdout_excerpt || null;
    }
    // pydantic 错:detail = [...]
    if (Array.isArray(d.detail)) {
      return d.detail
        .map((e) => {
          const x = e as { loc?: unknown[]; msg?: string };
          const loc = Array.isArray(x.loc) ? x.loc.join('.') : '';
          return loc ? `${loc}: ${x.msg ?? ''}` : (x.msg ?? '');
        })
        .filter(Boolean)
        .join('\n');
    }
    return null;
  };
  const detailText = renderDetail();

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/10 p-3">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-danger" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">上传失败</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{message}</p>
        </div>
      </div>

      {detailText ? (
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            详细信息
          </p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-card/40 p-3 font-mono text-[10px] text-muted-foreground">
            {detailText}
          </pre>
        </div>
      ) : null}

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onRetry}>
          重新选择文件
        </Button>
      </div>
    </div>
  );
}

export default UploadScriptDialog;
