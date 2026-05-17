/**
 * <Sparkline> — 极简数据曲线,KpiCard 内嵌使用
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.3、§ 8。
 *
 * 关键约束:
 *   - 无坐标轴 / 无 grid / 无 tooltip / 无 legend(纯装饰)
 *   - 颜色用 OKLCH chart-N CSS var,**不**硬编码
 *   - 默认 60x24,可被 KpiCard 撑大到 100% 宽度
 *   - 数据少于 2 个点直接返回空(避免 Recharts 报错)
 */
import { memo, useId, useMemo } from 'react';
import { Area, AreaChart, ResponsiveContainer } from 'recharts';

import { cn } from '@/lib/utils';

export interface SparklineProps {
  /** 数据点(纯 number 数组),从老到新 */
  data: number[];
  /** chart-N 的 N(1~5),默认 1(主色 Indigo) */
  variant?: 1 | 2 | 3 | 4 | 5;
  /** 容器宽,默认 100%(适应父容器) */
  width?: number | string;
  /** 容器高 */
  height?: number;
  className?: string;
}

function SparklineImpl({ data, variant = 1, width = '100%', height = 24, className }: SparklineProps) {
  const gradientId = useId();
  const stroke = `var(--chart-${variant})`;

  // 装成 Recharts 期望的对象数组;同时缓存避免每次 render 新建
  const points = useMemo(
    () => data.map((v, i) => ({ i, v: Number.isFinite(v) ? v : 0 })),
    [data],
  );

  if (points.length < 2) {
    return <div style={{ width, height }} className={cn('opacity-30', className)} />;
  }

  return (
    <div style={{ width, height }} className={className}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.32} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export const Sparkline = memo(SparklineImpl);
