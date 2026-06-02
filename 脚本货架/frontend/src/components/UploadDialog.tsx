/**
 * 上传脚本 zip(登录后):拖拽 + 点选,multipart 字段名 file,带 force 覆盖开关。
 */
import * as React from 'react';
import { useDropzone } from 'react-dropzone';
import { FileArchive, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { useUploadScript } from '@/api/hooks';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
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
  const upload = useUploadScript();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (!open) {
      setFile(null);
      setForce(false);
    }
  }, [open]);

  const onDrop = React.useCallback((accepted: File[]) => {
    const f = accepted[0];
    if (f) setFile(f);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: { 'application/zip': ['.zip'], 'application/x-zip-compressed': ['.zip'] },
  });

  const handleSubmit = async () => {
    if (!file) return;
    try {
      const res = await upload.mutateAsync({ file, force });
      toast.success(`${res.created ? '已上传' : '已更新'} ${res.name} v${res.version}`);
      onOpenChange(false);
      navigate(`/scripts/${encodeURIComponent(res.slug)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isUnauthorized) {
          toast.error('请先登录');
        } else if (err.code === 'conflict' || err.status === 409) {
          toast.error('该 slug 已存在,勾选「覆盖已存在」后重试');
        } else {
          toast.error(err.message);
        }
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
            上传符合货架规范的 .zip(含 manifest.yaml + main.py)。上限 4 MB。
          </DialogDescription>
        </DialogHeader>

        {file ? (
          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-4">
            <FileArchive className="h-8 w-8 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={() => setFile(null)} aria-label="移除">
              <X />
            </Button>
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
            <p className="text-sm font-medium">拖入 .zip 文件,或点击选择</p>
            <p className="text-xs text-muted-foreground">仅支持单个 zip</p>
          </div>
        )}

        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="force-switch" className="cursor-pointer">
              覆盖已存在
            </Label>
            <p className="text-xs text-muted-foreground">slug 相同时覆盖原脚本(force)</p>
          </div>
          <Switch id="force-switch" checked={force} onCheckedChange={setForce} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={!file || upload.isPending}>
            {upload.isPending ? '上传中…' : '上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
