/**
 * shadcn/ui 标准工具:cn(...) 用于条件 + 合并 className,
 * tailwind-merge 自动消除冲突的 utility(后者覆盖前者)。
 *
 * 用法:
 *   cn('px-4 py-2', isActive && 'bg-primary', className)
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
