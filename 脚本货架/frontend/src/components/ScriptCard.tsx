import { Link } from 'react-router-dom';
import { Download, FileText, SlidersHorizontal } from 'lucide-react';

import type { ScriptListItem } from '@/api/types';
import { categoryIcon } from '@/lib/categories';
import { ScriptIcon } from '@/components/ScriptIcon';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

/** 画廊脚本卡片。 */
export function ScriptCard({ script }: { script: ScriptListItem }) {
  return (
    <Link to={`/scripts/${encodeURIComponent(script.slug)}`} className="group block focus-visible:outline-none">
      <Card className="card-hover flex h-full flex-col p-5 group-focus-visible:ring-2 group-focus-visible:ring-ring">
        {/* 头部:图标 + 名称 + 版本 */}
        <div className="flex items-start gap-3">
          <ScriptIcon slug={script.slug} hasIcon={script.has_icon} size={44} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate font-semibold leading-tight">{script.name}</h3>
              <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                v{script.version}
              </Badge>
            </div>
            <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">{script.slug}</p>
          </div>
        </div>

        {/* 分类(有则显示,主色描边 + 图标,区别于下方 tags) */}
        {script.category && (
          <div className="mt-2.5">
            <CategoryBadge category={script.category} />
          </div>
        )}

        {/* 描述 */}
        <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">
          {script.description || '暂无描述'}
        </p>

        {/* 标签 */}
        {script.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {script.tags.slice(0, 4).map((t) => (
              <Badge key={t} variant="outline" className="text-[11px] font-normal">
                {t}
              </Badge>
            ))}
            {script.tags.length > 4 && (
              <Badge variant="outline" className="text-[11px] font-normal">
                +{script.tags.length - 4}
              </Badge>
            )}
          </div>
        )}

        {/* 底部统计 */}
        <div className="mt-auto flex items-center gap-4 pt-4 text-xs text-muted-foreground tabular-nums">
          <span className="flex items-center gap-1" title="配置字段数">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {script.field_count}
          </span>
          <span className="flex items-center gap-1" title="文件数">
            <FileText className="h-3.5 w-3.5" />
            {script.file_count}
          </span>
          <span className="flex items-center gap-1" title="下载次数">
            <Download className="h-3.5 w-3.5" />
            {script.download_count}
          </span>
        </div>
      </Card>
    </Link>
  );
}

/** 分类徽标:主色描边 + 分类图标,视觉上区别于普通 outline 标签。 */
export function CategoryBadge({ category }: { category: string }) {
  const Icon = categoryIcon(category);
  return (
    <Badge
      variant="outline"
      className="gap-1 border-primary/40 bg-primary/5 font-medium text-primary"
    >
      <Icon className="h-3 w-3" />
      {category}
    </Badge>
  );
}
