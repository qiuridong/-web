/**
 * 上传脚本 zip（登录后）。
 * 增强：下载模板 + 拖入后用 jszip+js-yaml 预校验 checklist + 格式说明，
 * 校验口径与签到管家一致（slug/version/必含文件），缺必填项禁用上传、明确提示。
 */
import * as React from 'react';
import { useDropzone } from 'react-dropzone';
import { CheckCircle2, Download, FileArchive, Loader2, Upload, X, XCircle } from 'lucide-react';
import JSZip from 'jszip';
import yaml from 'js-yaml';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { useUploadScript } from '@/api/hooks';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { SCRIPT_REQUIRED_FILES, buildTemplateZip, downloadBlob } from '@/lib/script-template';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

// 与货架/管家后端一致的口径
const SLUG_RE = /^[a-z][a-z0-9-]{0,40}$/;
const SEMVER_RE =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;

interface Check {
  label: string;
  ok: boolean;
  detail?: string;
}
interface Analysis {
  checks: Check[];
  canUpload: boolean;
}

async function analyzeZip(file: File): Promise<Analysis> {
  const zip = await JSZip.loadAsync(file);
  const allPaths = Object.entries(zip.files)
    .filter(([, v]) => !v.dir)
    .map(([k]) => k);
  // 自动剥离顶层单目录（如 GitHub 下载的 repo-main/）
  const tops = new Set(allPaths.map((p) => p.split('/')[0]));
  const hasTopDir = tops.size === 1 && allPaths.every((p) => p.includes('/'));
  const strip = (p: string) => (hasTopDir ? p.split('/').slice(1).join('/') : p);
  const rel = new Set(allPaths.map(strip));

  let manifest: Record<string, unknown> | undefined;
  let manifestError: string | undefined;
  const manifestPath = allPaths.find((p) => strip(p) === 'manifest.yaml');
  const manifestEntry = manifestPath ? zip.files[manifestPath] : undefined;
  if (manifestEntry) {
    try {
      const parsed = yaml.load(await manifestEntry.async('string'));
      if (parsed && typeof parsed === 'object') manifest = parsed as Record<string, unknown>;
      else manifestError = '不是有效的 YAML 映射';
    } catch (e) {
      manifestError = (e as Error).message;
    }
  }

  const slug = manifest?.slug;
  const name = manifest?.name;
  const version = manifest?.version;
  const slugOk = typeof slug === 'string' && SLUG_RE.test(slug);
  const versionOk = typeof version === 'string' && SEMVER_RE.test(version);

  const checks: Check[] = [
    { label: '含 manifest.yaml', ok: rel.has('manifest.yaml') },
    { label: '含 main.py', ok: rel.has('main.py') },
    {
      label: 'manifest 可解析',
      ok: !!manifest && !manifestError,
      detail: manifestError ? `解析失败：${manifestError}` : undefined,
    },
    {
      label: 'slug 合法',
      ok: slugOk,
      detail: slug == null ? '缺 slug' : slugOk ? String(slug) : `「${String(slug)}」需小写字母开头 / a-z0-9- / 长1-41`,
    },
    { label: 'name 非空', ok: typeof name === 'string' && name.length > 0, detail: name == null ? '缺 name' : undefined },
    {
      label: 'version 是 SemVer',
      ok: versionOk,
      detail: version == null ? '缺 version' : versionOk ? String(version) : `「${String(version)}」应形如 1.0.0`,
    },
  ];
  return { checks, canUpload: checks.every((c) => c.ok) };
}

export function UploadDialog({ trigger }: { trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <span onClick={() => setOpen(true)}>{trigger}</span>
      <UploadDialogBody open={open} onOpenChange={setOpen} />
    </>
  );
}

function UploadDialogBody({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [force, setForce] = React.useState(false);
  const [analysis, setAnalysis] = React.useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = React.useState(false);
  const upload = useUploadScript();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (!open) {
      setFile(null);
      setForce(false);
      setAnalysis(null);
      setAnalyzing(false);
    }
  }, [open]);

  const onDrop = React.useCallback((accepted: File[]) => {
    const f = accepted[0];
    if (!f) return;
    setFile(f);
    setAnalysis(null);
    setAnalyzing(true);
    analyzeZip(f)
      .then(setAnalysis)
      .catch((e) =>
        setAnalysis({ checks: [{ label: '读取 zip', ok: false, detail: (e as Error).message }], canUpload: false }),
      )
      .finally(() => setAnalyzing(false));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: { 'application/zip': ['.zip'], 'application/x-zip-compressed': ['.zip'] },
  });

  const downloadTemplate = async () => {
    try {
      downloadBlob(await buildTemplateZip(), 'my-script-template.zip');
    } catch {
      toast.error('生成模板失败');
    }
  };

  const handleSubmit = async () => {
    if (!file) return;
    try {
      const res = await upload.mutateAsync({ file, force });
      toast.success(`${res.created ? '已上传' : '已更新'} ${res.name} v${res.version}`);
      onOpenChange(false);
      navigate(`/scripts/${encodeURIComponent(res.slug)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isUnauthorized) toast.error('请先登录');
        else if (err.code === 'conflict' || err.status === 409)
          toast.error('该 slug 已存在，勾选「覆盖已存在」后重试');
        else toast.error(err.message);
      } else {
        toast.error('上传失败');
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>上传脚本</DialogTitle>
          <DialogDescription>
            上传符合格式的 .zip（与签到管家一致）。需含 manifest.yaml + main.py，单文件 ≤2MiB、总 ≤5MiB。
          </DialogDescription>
        </DialogHeader>

        {/* 格式速览 + 下载模板 */}
        <div className="rounded-lg border bg-muted/30 p-3 text-xs">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-medium text-foreground">脚本目录格式</span>
            <Button variant="outline" size="sm" className="h-7 gap-1" onClick={downloadTemplate}>
              <Download className="h-3.5 w-3.5" />
              下载模板
            </Button>
          </div>
          <ul className="space-y-1">
            {SCRIPT_REQUIRED_FILES.map((f) => (
              <li key={f.filename} className="flex gap-2">
                <code className="shrink-0 font-mono text-[11px] text-foreground">
                  {f.filename}
                  {f.required ? <span className="text-danger"> *</span> : ''}
                </code>
                <span className="text-muted-foreground">{f.hint}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-warning">
            ⚠️ main.py 顶部「dry-run 短路」段不能删，否则上传会被管家拒（HTTP 422）。模板里已写好。
          </p>
        </div>

        {/* 拖拽区 / 文件卡片 */}
        {file ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
              <FileArchive className="h-7 w-7 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
              </div>
              <Button variant="ghost" size="icon" onClick={() => { setFile(null); setAnalysis(null); }} aria-label="移除">
                <X />
              </Button>
            </div>

            {/* 预校验 checklist */}
            <div className="rounded-lg border p-3">
              {analyzing ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> 正在校验 zip…
                </p>
              ) : analysis ? (
                <ul className="space-y-1.5">
                  {analysis.checks.map((c) => (
                    <li key={c.label} className="flex items-start gap-2 text-sm">
                      {c.ok ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                      ) : (
                        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
                      )}
                      <span className={cn('min-w-0', c.ok ? 'text-foreground' : 'text-danger')}>
                        {c.label}
                        {c.detail && <span className="ml-1 text-xs text-muted-foreground">· {c.detail}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        ) : (
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors',
              isDragActive ? 'border-primary bg-primary/5' : 'hover:border-primary/50 hover:bg-muted/30',
            )}
          >
            <input {...getInputProps()} />
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">拖入 .zip 文件，或点击选择</p>
            <p className="text-xs text-muted-foreground">仅支持单个 zip，拖入后自动校验格式</p>
          </div>
        )}

        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="force-switch" className="cursor-pointer">覆盖已存在</Label>
            <p className="text-xs text-muted-foreground">slug 相同时覆盖原脚本（force）</p>
          </div>
          <Switch id="force-switch" checked={force} onCheckedChange={setForce} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={!file || analyzing || !analysis?.canUpload || upload.isPending}>
            {upload.isPending ? '上传中…' : !analysis?.canUpload && file && !analyzing ? '格式不符，无法上传' : '上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
