/**
 * <KpiCard> — 仪表盘顶部的数字卡(6 张)
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.3、§ 4(组件 props 表)、§ 8(美化手法)。
 *
 * 关键效果:
 *   - rounded-xl + border + bg-card + shadow-xs + card-hover
 *   - 数字 text-3xl font-semibold tabular-nums + framer-motion count-up 600ms
 *   - 可选 trend(↗/↘/—)+ 可选 sparkline(底部)
 *   - icon 24px(默认 lucide,strokeWidth 1.75)
 *   - hover 轻微抬升 + 阴影
 *
 * 设计稿没有"variant"概念(只有图表 chart-N),这里用 sparkline.variant 控制色相。
 * trend 文本颜色:正 → success,负 → danger,零 → muted-foreground。
 */
import { memo, useEffect, useState, type ComponentType } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { ArrowDownRight, ArrowUpRight, Minus, type LucideProps } from 'lucide-react';

import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Sparkline } from '@/components/common/Sparkline';
import { cn } from '@/lib/utils';

export interface KpiCardProps {
  title: string;
  /** number → 走 count-up 动画;string → 直接渲染(如 "98.4%") */
  value: number | string;
  /** number 模式下展示的后缀(如 '%' / '次') */
  unit?: string;
  /** lucide-react 图标组件,如 `Activity` */
  icon?: ComponentType<LucideProps>;
  trend?: {
    /** 数字变化(如 +0.6 表示 +0.6%);正负决定箭头与颜色 */
    value: number;
    /** 文案,如 "比昨日" */
    label: string;
    /** 是否在 value 上加百分号 */
    isPercent?: boolean;
  };
  sparkline?: number[];
  /** Sparkline 色相(chart-N) */
  sparklineVariant?: 1 | 2 | 3 | 4 | 5;
  /** 加载态,渲染 skeleton */
  loading?: boolean;
  className?: string;
}

/** 600ms count-up,仅 number value 启用 */
function CountUp({ to, suffix }: { to: number; suffix?: string }) {
  const motionValue = useMotionValue(0);
  // spring 让收尾更自然;duration 由 stiffness/damping 决定
  const spring = useSpring(motionValue, { stiffness: 90, damping: 22, mass: 0.6 });
  const display = useTransform(spring, (latest) => {
    // 整数:千分位;小数:保留至多 2 位(不强制),避免 "98.40%" → "98.4%"
    if (Number.isInteger(to)) {
      return new Intl.NumberFormat('zh-CN').format(Math.round(latest));
    }
    // 估算精度
    const fixed = latest.toFixed(2);
    return new Intl.NumberFormat('zh-CN').format(Number(fixed));
  });

  useEffect(() => {
    motionValue.set(to);
  }, [to, motionValue]);

  return (
    <span className="tabular-nums">
      <motion.span>{display}</motion.span>
      {suffix ? <span className="ml-0.5 text-xl text-muted-foreground">{suffix}</span> : null}
    </span>
  );
}

function trendColor(value: number): string {
  if (value > 0) return 'text-success';
  if (value < 0) return 'text-danger';
  return 'text-muted-foreground';
}

function KpiCardImpl({
  title,
  value,
  unit,
  icon: Icon,
  trend,
  sparkline,
  sparklineVariant = 1,
  loading,
  className,
}: KpiCardProps) {
  // 防 hydration / 初始 0 闪烁:首次 render 锁定一个稳定的初始值
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (loading) {
    return (
      <Card className={cn('h-32 p-5', className)}>
        <div className="flex items-start justify-between">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-5 w-5 rounded" />
        </div>
        <Skeleton className="mt-3 h-8 w-24" />
        <Skeleton className="mt-3 h-3 w-20" />
      </Card>
    );
  }

  const showCountUp = mounted && typeof value === 'number';
  const TrendIcon = trend ? (trend.value > 0 ? ArrowUpRight : trend.value < 0 ? ArrowDownRight : Minus) : null;

  return (
    <Card
      className={cn(
        'group relative h-32 overflow-hidden p-5',
        'transition-all duration-200 ease-[cubic-bezier(0.25,1,0.5,1)]',
        'hover:-translate-y-0.5 hover:shadow-md',
        className,
      )}
    >
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/80">
          {title}
        </span>
        {Icon ? (
          <Icon
            className="size-4 text-muted-foreground/60 transition-colors group-hover:text-primary"
            strokeWidth={1.75}
          />
        ) : null}
      </div>

      <div className="mt-2.5 flex items-baseline gap-1 text-3xl font-semibold tracking-tight text-foreground">
        {showCountUp ? (
          <CountUp to={value as number} suffix={unit} />
        ) : (
          <span className="tabular-nums">
            {typeof value === 'number' ? new Intl.NumberFormat('zh-CN').format(value) : value}
            {unit ? <span className="ml-0.5 text-xl text-muted-foreground">{unit}</span> : null}
          </span>
        )}
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-2">
        {trend ? (
          <div className={cn('flex items-center gap-1 text-xs font-medium', trendColor(trend.value))}>
            {TrendIcon ? <TrendIcon className="size-3.5" strokeWidth={2} /> : null}
            <span className="tabular-nums">
              {trend.value > 0 ? '+' : ''}
              {trend.value.toFixed(trend.isPercent ? 1 : 0)}
              {trend.isPercent ? '%' : ''}
            </span>
            <span className="text-muted-foreground/70">{trend.label}</span>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground/60">&nbsp;</span>
        )}

        {sparkline && sparkline.length >= 2 ? (
          <div className="pointer-events-none w-20 shrink-0">
            <Sparkline data={sparkline} variant={sparklineVariant} height={28} />
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export const KpiCard = memo(KpiCardImpl);
