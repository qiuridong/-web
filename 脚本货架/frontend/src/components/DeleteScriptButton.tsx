/**
 * 删除脚本(登录后):二次确认,要求输入 slug 防误删。
 */
import * as React from 'react';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { useDeleteScript } from '@/api/hooks';
import { Button } from '@/components/ui/button';
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

export function DeleteScriptButton({ slug, name }: { slug: string; name: string }) {
  const [open, setOpen] = React.useState(false);
  const [confirm, setConfirm] = React.useState('');
  const del = useDeleteScript();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (!open) setConfirm('');
  }, [open]);

  const handleDelete = async () => {
    try {
      await del.mutateAsync(slug);
      toast.success(`已删除 ${name}`);
      setOpen(false);
      navigate('/');
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        toast.error('请先登录');
      } else if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('删除失败');
      }
    }
  };

  return (
    <>
      <Button variant="outline" size="sm" className="text-destructive hover:bg-destructive/10" onClick={() => setOpen(true)}>
        <Trash2 />
        删除
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除脚本</DialogTitle>
            <DialogDescription>
              此操作不可撤销,将永久删除「{name}」及其全部文件。请输入 slug
              <span className="mx-1 font-mono font-semibold text-foreground">{slug}</span>
              确认。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="confirm-slug">确认 slug</Label>
            <Input
              id="confirm-slug"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder={slug}
              autoComplete="off"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={confirm !== slug || del.isPending}
            >
              {del.isPending ? '删除中…' : '确认删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
