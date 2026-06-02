import * as React from 'react';
import { Package } from 'lucide-react';

import { cn } from '@/lib/utils';
import { iconUrl } from '@/api/urls';

interface ScriptIconProps {
  slug: string;
  hasIcon: boolean;
  /** 像素尺寸 */
  size?: number;
  className?: string;
}

/**
 * 脚本图标:has_icon 时用 <img src=/api/.../icon>;
 * 404 或无图标回落 lucide 占位图标(Package)。
 */
export function ScriptIcon({ slug, hasIcon, size = 40, className }: ScriptIconProps) {
  const [errored, setErrored] = React.useState(false);
  const showImg = hasIcon && !errored;

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted/40 text-muted-foreground',
        className,
      )}
      style={{ width: size, height: size }}
    >
      {showImg ? (
        <img
          src={iconUrl(slug)}
          alt=""
          width={size}
          height={size}
          className="h-full w-full object-contain p-1"
          onError={() => setErrored(true)}
          loading="lazy"
        />
      ) : (
        <Package style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={1.6} />
      )}
    </div>
  );
}
