/**
 * shadcn/ui 标准工具:cn(...) 条件 + 合并 className(tailwind-merge 消冲突)。
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
