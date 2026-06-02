/**
 * 标签编辑(登录后):chip 列表 + 输入新增 + 删除,保存走 PATCH。
 */
import * as React from 'react';
import { Plus, X } from 'lucide-react';
import { toast } from 'sonner';

import { ApiError } from '@/api/client';
import { useUpdateTags } from '@/api/hooks';
import { Badge } from '@/components/ui/badge';
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

export function TagEditor({ slug, tags, trigger }: { slug: string; tags: string[]; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <span onClick={() => setOpen(true)}>{trigger}</span>
      {open && <TagEditorBody slug={slug} initialTags={tags} open={open} onOpenChange={setOpen} />}
    </>
  );
}

function TagEditorBody({
  slug,
  initialTags,
  open,
  onOpenChange,
}: {
  slug: string;
  initialTags: string[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [draft, setDraft] = React.useState<string[]>(initialTags);
  const [input, setInput] = React.useState('');
  const updateTags = useUpdateTags(slug);

  const addTag = () => {
    const t = input.trim();
    if (!t) return;
    if (!draft.includes(t)) setDraft((p) => [...p, t]);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag();
    }
  };

  const handleSave = async () => {
    try {
      await updateTags.mutateAsync(draft);
      toast.success('标签已更新');
      onOpenChange(false);
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>编辑标签</DialogTitle>
          <DialogDescription>添加或移除标签,用于画廊筛选。</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap gap-1.5">
          {draft.length === 0 && <p className="text-sm text-muted-foreground">暂无标签</p>}
          {draft.map((t) => (
            <Badge key={t} variant="secondary" className="gap-1 pr-1">
              {t}
              <button
                type="button"
                onClick={() => setDraft((p) => p.filter((x) => x !== t))}
                className="rounded-full p-0.5 hover:bg-background/50"
                aria-label={`移除 ${t}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>

        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入标签后回车"
          />
          <Button type="button" variant="outline" size="icon" onClick={addTag} aria-label="添加标签">
            <Plus />
          </Button>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={updateTags.isPending}>
            {updateTags.isPending ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
