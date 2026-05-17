/**
 * <CronInput> — Cron 表达式输入
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.6、§ 4。
 *
 * 内部:
 *   - shadcn <Input> 接收 cron 表达式
 *   - cronstrue 翻译为中文描述,显示在输入框下方
 *   - **MVP-3B 升级**:用 cron-parser 5.x `CronExpressionParser.parse(expr, { tz, currentDate })` 算未来执行,
 *     替换自写迭代器。支持完整 cron 语义(步长 / 区间 / 列表 / L / W / 5+1 段等)。
 *   - 失败时 inline error(红字)
 *   - 常用预设 Popover(每天/工作日/每周一/每月1号)
 *
 * 注意:
 *   - 这里只做"前端校验提示";后端 APScheduler 的 CronTrigger 校验为最终真相
 *   - 时区取自 useSettings().timezone(默认 Asia/Shanghai),与后端调度计算一致
 *   - cron-parser 5.x 默认支持 5 段(分时日月周)与 6 段(秒分时日月周),自动识别
 */
import { forwardRef, useId, useMemo, type ChangeEvent } from 'react';
import cronstrue from 'cronstrue/i18n';
import { CronExpressionParser } from 'cron-parser';
import { CalendarClock, ChevronDown } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useSettings } from '@/api/hooks/settings';
import { formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface CronInputProps {
  name?: string;
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  disabled?: boolean;
  readOnly?: boolean;
  className?: string;
  onChange?: (next: string) => void;
  onBlur?: () => void;
  id?: string;
  /** 是否展示下方解释与未来执行 */
  showHelper?: boolean;
}

interface CronPreset {
  label: string;
  expr: string;
}

const PRESETS: CronPreset[] = [
  { label: '每天 09:00', expr: '0 9 * * *' },
  { label: '每天 早 7:00', expr: '0 7 * * *' },
  { label: '工作日 09:00', expr: '0 9 * * 1-5' },
  { label: '每周一 09:00', expr: '0 9 * * 1' },
  { label: '每月 1 号 09:00', expr: '0 9 1 * *' },
  { label: '每小时整点', expr: '0 * * * *' },
  { label: '每 30 分钟', expr: '*/30 * * * *' },
];

interface CronInfo {
  ok: boolean;
  human?: string;
  upcoming?: string[];
  error?: string;
}

/**
 * 用 cron-parser 算未来 3 次执行(按指定时区)。
 *
 * - cron-parser 5.x API:`CronExpressionParser.parse(expr, { tz, currentDate })`
 * - 返回的 CronDate 实现 toDate() 方法,转回 JS Date 后用 date-fns 格式化
 * - tz 失败时不抛(库内自动 fallback UTC),保险起见也 catch 一次
 */
function parseCron(expr: string, timezone: string | undefined): CronInfo {
  const trimmed = expr.trim();
  if (!trimmed) {
    return { ok: false, error: '留空' };
  }
  try {
    const human = cronstrue.toString(trimmed, {
      locale: 'zh_CN',
      use24HourTimeFormat: true,
      throwExceptionOnParseError: true,
    });
    const upcoming: string[] = [];
    try {
      const parsed = CronExpressionParser.parse(trimmed, {
        currentDate: new Date(),
        ...(timezone ? { tz: timezone } : {}),
      });
      const occs = parsed.take(3);
      for (const occ of occs) {
        // CronDate.toDate() 返回 JS Date(已带时区偏移)
        upcoming.push(formatDate(occ.toDate(), 'MM-dd HH:mm'));
      }
    } catch {
      // cron-parser 不支持的扩展(如 ? / 复杂 L)— 只显示 human description
    }
    return { ok: true, human, upcoming };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg };
  }
}

export const CronInput = forwardRef<HTMLInputElement, CronInputProps>(function CronInput(
  {
    name,
    value,
    defaultValue,
    placeholder = '例如 0 9 * * *',
    disabled,
    readOnly,
    className,
    onChange,
    onBlur,
    id,
    showHelper = true,
  },
  ref,
) {
  const reactId = useId();
  const inputId = id ?? `cron-${reactId}`;
  const { data: settings } = useSettings();
  const timezone = (settings?.timezone?.value as string | undefined) ?? 'Asia/Shanghai';
  const info = useMemo(
    () => parseCron(value ?? defaultValue ?? '', timezone),
    [value, defaultValue, timezone],
  );

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    onChange?.(e.target.value);
  }

  function applyPreset(expr: string) {
    onChange?.(expr);
  }

  return (
    <div className={cn('flex w-full flex-col gap-1.5', className)}>
      <div className="flex items-center gap-2">
        <Input
          ref={ref}
          id={inputId}
          name={name}
          value={value}
          defaultValue={defaultValue}
          placeholder={placeholder}
          disabled={disabled}
          readOnly={readOnly}
          onChange={handleChange}
          onBlur={onBlur}
          autoComplete="off"
          spellCheck={false}
          className="h-10 font-mono text-sm tabular-nums"
        />
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-10 shrink-0 gap-1.5"
              disabled={disabled}
            >
              <CalendarClock className="size-3.5" strokeWidth={1.75} />
              <span>预设</span>
              <ChevronDown className="size-3" strokeWidth={1.75} />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 p-2">
            <div className="mb-1 px-1.5 text-[11px] uppercase tracking-wider text-muted-foreground/70">
              常用 cron
            </div>
            <ul className="flex flex-col">
              {PRESETS.map((p) => (
                <li key={p.expr}>
                  <button
                    type="button"
                    onClick={() => applyPreset(p.expr)}
                    className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <span>{p.label}</span>
                    <code className="font-mono text-[11px] text-muted-foreground">
                      {p.expr}
                    </code>
                  </button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      </div>

      {showHelper ? (
        <div className="min-h-[1.25rem] text-xs">
          {value && value.trim() ? (
            info.ok ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                <span className="text-foreground">{info.human}</span>
                {info.upcoming && info.upcoming.length > 0 ? (
                  <span className="text-muted-foreground/80 tabular-nums">
                    下次:{info.upcoming.join(' / ')}
                  </span>
                ) : null}
              </div>
            ) : (
              <span className="text-danger">
                cron 解析失败:{info.error ?? '格式不正确'}
              </span>
            )
          ) : (
            <span className="text-muted-foreground/60">
              支持完整 cron(5 段 或 6 段);时区 {timezone};示例 `0 9 * * *` = 每天 9 点
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
});

export default CronInput;
