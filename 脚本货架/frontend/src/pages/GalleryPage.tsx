import * as React from 'react';
import { PackageOpen, Search, Upload } from 'lucide-react';

import { useScripts } from '@/api/hooks';
import { useAuth } from '@/auth/AuthProvider';
import { CATEGORIES, UNCATEGORIZED, categoryIcon } from '@/lib/categories';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { ScriptCard } from '@/components/ScriptCard';
import { UploadDialog } from '@/components/UploadDialog';
import { EmptyState, ErrorState } from '@/components/States';

export function GalleryPage() {
  const { data, isLoading, isError, error, refetch } = useScripts();
  const { user } = useAuth();
  const [query, setQuery] = React.useState('');
  const [activeTags, setActiveTags] = React.useState<string[]>([]);
  // 分类筛选(单选):null = 全部;UNCATEGORIZED = 未分类;否则具体分类名
  const [activeCategory, setActiveCategory] = React.useState<string | null>(null);

  // 聚合所有标签
  const allTags = React.useMemo(() => {
    const set = new Set<string>();
    data?.forEach((s) => s.tags.forEach((t) => set.add(t)));
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [data]);

  // 实际出现的分类(用于:仅展示有内容的分类 chip + 是否需要「未分类」chip)
  const presentCategories = React.useMemo(() => {
    const set = new Set<string>();
    let hasUncategorized = false;
    data?.forEach((s) => {
      if (s.category) set.add(s.category);
      else hasUncategorized = true;
    });
    // 按预设顺序排列预设分类,自定义分类(若有)追加在后
    const ordered = CATEGORIES.filter((c) => set.has(c));
    const extras = [...set].filter((c) => !(CATEGORIES as readonly string[]).includes(c)).sort();
    return { categories: [...ordered, ...extras], hasUncategorized };
  }, [data]);

  // 过滤:name/description/slug/category 搜索 + 分类(单选) + 标签(AND)
  const filtered = React.useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.filter((s) => {
      if (q) {
        const hay = `${s.name} ${s.description ?? ''} ${s.slug} ${s.category ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (activeCategory === UNCATEGORIZED) {
        if (s.category) return false;
      } else if (activeCategory !== null && s.category !== activeCategory) {
        return false;
      }
      if (activeTags.length > 0 && !activeTags.every((t) => s.tags.includes(t))) {
        return false;
      }
      return true;
    });
  }, [data, query, activeCategory, activeTags]);

  const toggleTag = (tag: string) => {
    setActiveTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  };

  return (
    <div className="space-y-6">
      {/* 标题 + 上传 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">脚本画廊</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            浏览所有签到脚本,点击查看详情、下载或一键导入到签到管家。
          </p>
        </div>
        {user && (
          <UploadDialog
            trigger={
              <Button>
                <Upload />
                上传脚本
              </Button>
            }
          />
        )}
      </div>

      {/* 搜索 + 标签筛选 */}
      <div className="space-y-3">
        <div className="relative max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索名称、描述、slug、分类…"
            className="pl-9"
          />
        </div>

        {/* 分类筛选(单选) */}
        {(presentCategories.categories.length > 0 || presentCategories.hasUncategorized) && (
          <div className="flex flex-wrap gap-1.5">
            <CategoryChip
              label="全部"
              active={activeCategory === null}
              onClick={() => setActiveCategory(null)}
            />
            {presentCategories.categories.map((cat) => {
              const Icon = categoryIcon(cat);
              return (
                <CategoryChip
                  key={cat}
                  label={cat}
                  icon={<Icon className="h-3.5 w-3.5" />}
                  active={activeCategory === cat}
                  onClick={() => setActiveCategory(cat)}
                />
              );
            })}
            {presentCategories.hasUncategorized && (
              <CategoryChip
                label="未分类"
                active={activeCategory === UNCATEGORIZED}
                onClick={() => setActiveCategory(UNCATEGORIZED)}
              />
            )}
          </div>
        )}

        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {allTags.map((tag) => {
              const active = activeTags.includes(tag);
              return (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                    active
                      ? 'border-transparent bg-primary text-primary-foreground'
                      : 'border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )}
                >
                  {tag}
                </button>
              );
            })}
            {activeTags.length > 0 && (
              <button
                type="button"
                onClick={() => setActiveTags([])}
                className="rounded-full px-3 py-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
              >
                清除筛选
              </button>
            )}
          </div>
        )}
      </div>

      {/* 内容 */}
      {isLoading ? (
        <CardGridSkeleton />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => void refetch()} />
      ) : filtered.length === 0 ? (
        data && data.length === 0 ? (
          <EmptyState
            icon={<PackageOpen className="h-10 w-10" />}
            title="货架还是空的"
            description={user ? '点击右上角「上传脚本」添加第一个脚本。' : '登录后即可上传脚本。'}
          />
        ) : (
          <EmptyState
            icon={<Search className="h-10 w-10" />}
            title="没有匹配的脚本"
            description="试试调整搜索词,或切换分类 / 清除标签筛选。"
          />
        )
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((s) => (
            <ScriptCard key={s.slug} script={s} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 分类筛选 chip(单选高亮,主色填充)。 */
function CategoryChip({
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
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
        active
          ? 'border-transparent bg-primary text-primary-foreground shadow-sm'
          : 'border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function CardGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card p-5">
          <div className="flex items-start gap-3">
            <Skeleton className="h-11 w-11 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
          <Skeleton className="mt-4 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-5/6" />
          <div className="mt-4 flex gap-2">
            <Skeleton className="h-5 w-12 rounded-full" />
            <Skeleton className="h-5 w-12 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
