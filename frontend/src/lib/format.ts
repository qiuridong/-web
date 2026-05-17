/**
 * 格式化工具
 *
 * 设计稿契约:`进度/设计/前端UI设计.md` § 1.1.5(时间显示规则)。
 * 统一 ISO 解析 + 相对/绝对显示。
 */
import { format, formatDistanceToNowStrict, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';

/**
 * 格式化为绝对时间,默认 'yyyy-MM-dd HH:mm'。
 *
 * @param input ISO 字符串 / Date / number(epoch ms)
 * @param pattern date-fns format pattern
 */
export function formatDate(
  input: string | number | Date | null | undefined,
  pattern = 'yyyy-MM-dd HH:mm',
): string {
  if (input === null || input === undefined) return '—';
  let d: Date;
  if (typeof input === 'string') {
    d = parseISO(input);
  } else if (typeof input === 'number') {
    d = new Date(input);
  } else {
    d = input;
  }
  if (Number.isNaN(d.getTime())) return '—';
  return format(d, pattern, { locale: zhCN });
}

/**
 * 格式化为相对时间,如 "3 分钟前" / "刚刚"。
 *
 * 注意 date-fns 中文区在 < 30 秒时会输出"几秒前",我们改成"刚刚"以贴合设计稿。
 */
export function formatRelative(input: string | number | Date | null | undefined): string {
  if (input === null || input === undefined) return '—';
  let d: Date;
  if (typeof input === 'string') {
    d = parseISO(input);
  } else if (typeof input === 'number') {
    d = new Date(input);
  } else {
    d = input;
  }
  if (Number.isNaN(d.getTime())) return '—';
  const diffSec = (Date.now() - d.getTime()) / 1000;
  if (diffSec < 30 && diffSec >= 0) return '刚刚';
  return formatDistanceToNowStrict(d, { addSuffix: true, locale: zhCN });
}

/**
 * 格式化字节数为可读字符串(SI 千进制不准确,这里用 IEC 1024 进制 + KiB/MiB)。
 *
 * TODO(Batch 4/5 编码 agent):若设计稿后续指定走 SI(KB/MB),改为 1000 进制。
 */
export function formatBytes(bytes: number | null | undefined, fractionDigits = 1): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let size = bytes / 1024;
  let unitIdx = 0;
  while (size >= 1024 && unitIdx < units.length - 1) {
    size /= 1024;
    unitIdx += 1;
  }
  return `${size.toFixed(fractionDigits)} ${units[unitIdx]}`;
}

/**
 * 格式化时长(毫秒)为 "1m 23s" / "523ms" 风格。
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms) || ms < 0) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalSec = Math.floor(ms / 1000);
  const sec = totalSec % 60;
  const min = Math.floor(totalSec / 60) % 60;
  const hr = Math.floor(totalSec / 3600);
  const parts: string[] = [];
  if (hr > 0) parts.push(`${hr}h`);
  if (min > 0) parts.push(`${min}m`);
  parts.push(`${sec}s`);
  return parts.join(' ');
}
