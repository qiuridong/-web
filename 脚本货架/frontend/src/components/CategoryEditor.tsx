/**
 * 分类编辑(登录后):弹窗内 10 预设分类 + 「未分类」按钮网格,单选,保存走 PATCH {category}。
 * category 传 "" 清为未分类,传分类名设置(参考 TagEditor 的交互)。
 */
import * as React from 'react';
import { toast } from 'sonner';

import { ApiError } from '@/api/client';
import { useUpdateCategory } from '@/api/hooks';
import { CATEGORIES, categoryIcon } from '@/lib/categories';
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

export function CategoryEditor({
  slug,
  category,
  trigger,
}: {
  slug: string;
  category: string | null;
  trigger: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <span onClick={() => setOpen(true)}>{trigger}</span>
      {open && (
        <CategoryEditorBody slug={slug} initial={category} open={open} onOpenChange={setOpen} />
      )}
    </>
  );
}

function CategoryEditorBody({
  slug,
  initial,
  open,
  onOpenChange,
}: {
  slug: string;
  initial: string | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  // null 表示「未分类」
  const [selected, setSelected] = React.useState<string | null>(initial);
  const update = useUpdateCategory(slug);

  const handleSave = async () => {
    try {
      // 后端契约:"" 清为未分类,分类名设置
      await update.mutateAsync(selected ?? '');
      toast.success('分类已更新');
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
          <DialogTitle>设置分类</DialogTitle>
          <DialogDescription>为脚本选择一个分类,用于画廊筛选。每个脚本仅一个分类。</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <CategoryOption
            label="未分类"
            active={selected === null}
            onClick={() => setSelected(null)}
          />
          {CATEGORIES.map((cat) => {
            const Icon = categoryIcon(cat);
            return (
              <CategoryOption
                key={cat}
                label={cat}
                icon={<Icon className="h-4 w-4" />}
                active={selected === cat}
                onClick={() => setSelected(cat)}
              />
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={update.isPending}>
            {update.isPending ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CategoryOption({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon?: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  );
}
