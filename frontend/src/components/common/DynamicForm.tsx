/**
 * <DynamicForm> — 按 fields_schema 动态渲染实例配置表单
 *
 * 设计契约:
 *   - 字段类型表:`进度/设计/前端UI设计.md` § 3.6 + `进度/设计/后端架构.md` § 3.2
 *   - secret 字段 PATCH 语义:已配置 + 未 touch 则前端不发送(让后端保留原值)
 *
 * 输入:
 *   - fields: ScriptField[]
 *   - initialValues: 已有值(create 留空,edit 由后端 detail 提供;secret 字段值固定为 ''(后端 null))
 *   - secretsSet: Record<key, boolean> 来自后端 _secret_set
 *   - 顶部 prefix children:用于嵌入 instance 元信息字段(name / cron_expr / timeout_sec 等)
 *   - onSubmit: 提交回调(已剔除空 secret + 类型已归一)
 *
 * 注意:
 *   - 字段分组(field.group)折叠展示
 *   - 必填 *
 *   - description 通过下方小字展示;长描述用 Tooltip(hover question icon)
 *   - 不直接 import shadcn <Form> wrapper(它强依赖 RHF FormProvider),
 *     而是手动用 useForm + Controller 渲染,因为字段类型动态、不便走 <FormField name=...> 静态语法
 */
import { useMemo, useState, type ReactNode } from 'react';
import { Controller, useForm, type Control, type FieldValues, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z, ZodIssueCode, type ZodSchema, type ZodTypeAny } from 'zod';
import {
  AlertCircle,
  ChevronDown,
  HelpCircle,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';

import CronInput from '@/components/common/CronInput';
import SecretInput from '@/components/common/SecretInput';
import type {
  ScriptField,
  ScriptFieldOption,
  ScriptFieldType,
} from '@/api/hooks/scripts';
import { cn } from '@/lib/utils';

export interface DynamicFormProps {
  fields: ScriptField[];
  initialValues?: Record<string, unknown>;
  /** 来自后端 _secret_set:标记哪些 secret 字段已存值(决定 SecretInput 是否显示 "已配置" 占位 + PATCH 时是否提交) */
  secretsSet?: Record<string, boolean>;
  /** 表单顶部插入额外字段(实例 name / description / cron_expr / timeout_sec 等) */
  prefix?: ReactNode;
  /** 提交回调;返回值/错误由调用方处理(toast 等) */
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void;
  /** 提交按钮文字 */
  submitLabel?: string;
  /** 取消按钮回调(若传则显示取消) */
  onCancel?: () => void;
  /** 表单模式 — 'create' 不会做 secret 占位提示;'edit' 会 */
  mode?: 'create' | 'edit';
  className?: string;
  /** 提交进行中(由调用方控制,优先于内部 isSubmitting) */
  isPending?: boolean;
}

/* ============ 字段 → zod schema 构造 ============ */

function buildFieldSchema(field: ScriptField, isEdit: boolean, secretSet: boolean): ZodTypeAny {
  switch (field.type) {
    case 'string':
    case 'url':
    case 'multiline':
    case 'cron':
    case 'secret': {
      let s = z.string();
      if (field.type === 'url') s = s.url('请输入合法 URL');
      if (typeof field.min_length === 'number') {
        s = s.min(field.min_length, `至少 ${field.min_length} 个字符`);
      }
      if (typeof field.max_length === 'number') {
        s = s.max(field.max_length, `至多 ${field.max_length} 个字符`);
      }
      if (field.pattern) {
        try {
          const re = new RegExp(field.pattern);
          s = s.regex(re, '不符合正则要求');
        } catch {
          // ignore bad pattern
        }
      }
      // 必填校验:secret 字段在 edit 模式 + 已存值 → 留空合法(让后端保留原值)
      if (field.required) {
        if (field.type === 'secret' && isEdit && secretSet) {
          return s.optional();
        }
        return s.min(1, '必填');
      }
      return s.optional();
    }
    case 'integer': {
      // input 给字符串/数字混入;统一 preprocess
      let base = z.number({ message: '请输入数字' });
      if (typeof field.min === 'number') {
        base = base.min(field.min, `不能小于 ${field.min}`);
      }
      if (typeof field.max === 'number') {
        base = base.max(field.max, `不能大于 ${field.max}`);
      }
      base = base.int('必须是整数');
      const pre = z.preprocess((v) => {
        if (v === '' || v === null || v === undefined) return undefined;
        if (typeof v === 'string') {
          const n = Number(v);
          return Number.isNaN(n) ? v : n;
        }
        return v;
      }, base);
      if (field.required) {
        return pre.refine((v) => v !== undefined && v !== null, { message: '必填' });
      }
      return pre.optional();
    }
    case 'boolean': {
      // bool 总是提交;required 不影响
      return z.boolean();
    }
    case 'select': {
      const values = (field.options ?? []).map((o) => o.value);
      let s: ZodSchema<string>;
      if (values.length > 0) {
        // 用 enum 校验
        s = z.enum(values as [string, ...string[]]);
      } else {
        s = z.string();
      }
      if (field.required) return s as ZodTypeAny;
      return (s as ZodTypeAny).optional();
    }
    case 'multiselect': {
      const values = (field.options ?? []).map((o) => o.value);
      const itemSchema =
        values.length > 0
          ? z.enum(values as [string, ...string[]])
          : z.string();
      let arr = z.array(itemSchema);
      if (typeof field.min_items === 'number') {
        arr = arr.min(field.min_items, `至少选 ${field.min_items} 项`);
      }
      if (typeof field.max_items === 'number') {
        arr = arr.max(field.max_items, `至多选 ${field.max_items} 项`);
      }
      if (field.required) {
        return arr.min(Math.max(1, field.min_items ?? 1), '必填');
      }
      return arr.optional();
    }
    case 'json': {
      // 字符串输入,提交时尝试 JSON.parse;失败 → 校验错
      return z.string().superRefine((val, ctx) => {
        if (!val || !val.trim()) {
          if (field.required) {
            ctx.addIssue({ code: ZodIssueCode.custom, message: '必填' });
          }
          return;
        }
        try {
          JSON.parse(val);
        } catch (err) {
          ctx.addIssue({
            code: ZodIssueCode.custom,
            message: 'JSON 解析失败:' + (err instanceof Error ? err.message : String(err)),
          });
        }
      });
    }
    default:
      return z.unknown();
  }
}

function buildFormSchema(
  fields: ScriptField[],
  mode: 'create' | 'edit',
  secretsSet: Record<string, boolean>,
): ZodSchema<FieldValues> {
  const shape: Record<string, ZodTypeAny> = {};
  for (const f of fields) {
    shape[f.key] = buildFieldSchema(f, mode === 'edit', !!secretsSet[f.key]);
  }
  return z.object(shape) as ZodSchema<FieldValues>;
}

/* ============ 默认值构造 ============ */

function buildDefaults(
  fields: ScriptField[],
  initial: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (Object.prototype.hasOwnProperty.call(initial, f.key)) {
      const v = initial[f.key];
      if (f.type === 'json' && v !== null && v !== undefined && typeof v !== 'string') {
        out[f.key] = JSON.stringify(v, null, 2);
      } else if (v === null) {
        // secret 字段后端返回 null;表单显示空字符串
        out[f.key] = f.type === 'boolean' ? false : '';
      } else {
        out[f.key] = v;
      }
    } else if (f.default !== undefined && f.default !== null) {
      if (f.type === 'json' && typeof f.default !== 'string') {
        out[f.key] = JSON.stringify(f.default, null, 2);
      } else {
        out[f.key] = f.default;
      }
    } else {
      switch (f.type) {
        case 'boolean':
          out[f.key] = false;
          break;
        case 'multiselect':
          out[f.key] = [];
          break;
        case 'integer':
          out[f.key] = '';
          break;
        default:
          out[f.key] = '';
          break;
      }
    }
  }
  return out;
}

/* ============ 字段分组工具 ============ */

interface FieldGroup {
  name: string;
  /** 无 group 字段并入"配置" */
  fields: ScriptField[];
}

function groupFields(fields: ScriptField[]): FieldGroup[] {
  const map = new Map<string, ScriptField[]>();
  for (const f of fields) {
    const g = (f.group ?? '配置').trim() || '配置';
    if (!map.has(g)) map.set(g, []);
    map.get(g)!.push(f);
  }
  return Array.from(map.entries()).map(([name, fs]) => ({ name, fields: fs }));
}

/* ============ Combobox 多选 ============ */

interface MultiSelectComboboxProps {
  options: ScriptFieldOption[];
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

function MultiSelectCombobox({
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: MultiSelectComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = new Set(value ?? []);

  function toggle(v: string) {
    const next = new Set(selected);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange(Array.from(next));
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-auto min-h-10 w-full justify-between gap-2 px-3 text-left font-normal"
          disabled={disabled}
        >
          <div className="flex flex-1 flex-wrap items-center gap-1">
            {selected.size === 0 ? (
              <span className="text-muted-foreground">{placeholder ?? '请选择'}</span>
            ) : (
              Array.from(selected).map((v) => {
                const opt = options.find((o) => o.value === v);
                return (
                  <Badge key={v} variant="secondary" className="font-normal">
                    {opt?.label ?? v}
                  </Badge>
                );
              })
            )}
          </div>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput placeholder="搜索…" />
          <CommandList>
            <CommandEmpty>无匹配项</CommandEmpty>
            <CommandGroup>
              {options.map((opt) => {
                const checked = selected.has(opt.value);
                return (
                  <CommandItem
                    key={opt.value}
                    value={opt.value}
                    onSelect={() => toggle(opt.value)}
                    className="cursor-pointer"
                  >
                    <span
                      className={cn(
                        'mr-2 inline-flex size-4 items-center justify-center rounded border border-border text-[10px]',
                        checked && 'border-primary bg-primary text-primary-foreground',
                      )}
                      aria-hidden
                    >
                      {checked ? '✓' : ''}
                    </span>
                    <div className="flex flex-col">
                      <span>{opt.label}</span>
                      {opt.description ? (
                        <span className="text-xs text-muted-foreground">{opt.description}</span>
                      ) : null}
                    </div>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/* ============ 字段渲染 ============ */

interface FieldRendererProps {
  field: ScriptField;
  control: Control<FieldValues>;
  isSecretSet: boolean;
  mode: 'create' | 'edit';
  /** 由 DynamicForm 维护:secret 字段是否 touch(决定 PATCH 时是否提交) */
  onSecretTouch?: () => void;
}

function FieldRenderer({ field, control, isSecretSet, mode, onSecretTouch }: FieldRendererProps) {
  return (
    <Controller
      name={field.key}
      control={control}
      render={({ field: rhfField, fieldState }) => {
        const error = fieldState.error?.message;
        const id = `field-${field.key}`;
        return (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor={id} className="text-sm font-medium">
                {field.label}
                {field.required ? (
                  <span className="ml-0.5 text-danger" aria-label="必填">
                    *
                  </span>
                ) : null}
              </Label>
              <FieldTypeTag type={field.type} />
              {field.description ? (
                <TooltipProvider delayDuration={150}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button type="button" className="text-muted-foreground/70 hover:text-foreground">
                        <HelpCircle className="size-3.5" strokeWidth={1.75} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs whitespace-pre-line">
                      {field.description}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : null}
            </div>

            <FieldControl
              field={field}
              id={id}
              value={rhfField.value}
              onChange={rhfField.onChange}
              onBlur={rhfField.onBlur}
              isSecretSet={isSecretSet}
              mode={mode}
              onSecretTouch={onSecretTouch}
            />

            {error ? (
              <p
                className="flex items-center gap-1 text-xs text-danger"
                role="alert"
              >
                <AlertCircle className="size-3" strokeWidth={1.75} />
                {error}
              </p>
            ) : null}
          </div>
        );
      }}
    />
  );
}

interface FieldControlProps {
  field: ScriptField;
  id: string;
  value: unknown;
  onChange: (next: unknown) => void;
  onBlur: () => void;
  isSecretSet: boolean;
  mode: 'create' | 'edit';
  onSecretTouch?: () => void;
}

function FieldControl({
  field,
  id,
  value,
  onChange,
  onBlur,
  isSecretSet,
  mode,
  onSecretTouch,
}: FieldControlProps) {
  switch (field.type) {
    case 'string':
    case 'url':
      return (
        <Input
          id={id}
          type={field.type === 'url' ? 'url' : 'text'}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={field.placeholder}
          className="h-10"
        />
      );
    case 'secret':
      return (
        <SecretInput
          id={id}
          value={(value as string) ?? ''}
          onChange={onChange}
          onBlur={onBlur}
          isSet={isSecretSet}
          mode={mode}
          placeholder={field.placeholder}
          onTouched={onSecretTouch}
        />
      );
    case 'integer': {
      const numValue = value === '' || value === undefined ? '' : String(value);
      const showSlider =
        typeof field.min === 'number' && typeof field.max === 'number' && field.max > field.min;
      return (
        <div className={cn(showSlider ? 'grid grid-cols-[1fr,auto] gap-3' : '')}>
          {showSlider ? (
            <Slider
              value={[Number(numValue || field.min || 0)]}
              min={field.min}
              max={field.max}
              step={field.step ?? 1}
              onValueChange={(arr) => onChange(arr[0])}
              className="my-3"
            />
          ) : null}
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            value={numValue}
            onChange={(e) => onChange(e.target.value)}
            onBlur={onBlur}
            placeholder={field.placeholder}
            min={field.min}
            max={field.max}
            step={field.step ?? 1}
            className={cn('h-10 tabular-nums', showSlider && 'w-24 text-right')}
          />
        </div>
      );
    }
    case 'boolean':
      return (
        <div className="flex items-center gap-2 pt-1">
          <Switch
            id={id}
            checked={!!value}
            onCheckedChange={(b) => onChange(b)}
          />
          <span className="text-xs text-muted-foreground">
            {value ? '已开启' : '已关闭'}
          </span>
        </div>
      );
    case 'select':
      return (
        <Select
          value={(value as string) ?? ''}
          onValueChange={(v) => onChange(v)}
        >
          <SelectTrigger id={id} className="h-10">
            <SelectValue placeholder={field.placeholder ?? '请选择'} />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                <span>{opt.label}</span>
                {opt.description ? (
                  <span className="ml-2 text-xs text-muted-foreground">
                    {opt.description}
                  </span>
                ) : null}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    case 'multiselect':
      return (
        <MultiSelectCombobox
          options={field.options ?? []}
          value={(value as string[]) ?? []}
          onChange={(v) => onChange(v)}
          placeholder={field.placeholder ?? '请选择(多选)'}
        />
      );
    case 'multiline':
      return (
        <Textarea
          id={id}
          rows={field.rows ?? 4}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={field.placeholder}
        />
      );
    case 'cron':
      return (
        <CronInput
          id={id}
          value={(value as string) ?? ''}
          onChange={(v) => onChange(v)}
          onBlur={onBlur}
          placeholder={field.placeholder ?? '例如 0 9 * * *'}
        />
      );
    case 'json':
      return (
        <Textarea
          id={id}
          rows={field.rows ?? 6}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={field.placeholder ?? '{ "key": "value" }'}
          className="font-mono text-xs"
          spellCheck={false}
        />
      );
    default:
      return (
        <Input
          id={id}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          className="h-10"
        />
      );
  }
}

function FieldTypeTag({ type }: { type: ScriptFieldType }) {
  const colorMap: Record<ScriptFieldType, string> = {
    string: 'chart-1',
    secret: 'chart-5',
    integer: 'chart-2',
    boolean: 'chart-3',
    select: 'chart-4',
    multiselect: 'chart-4',
    multiline: 'chart-1',
    cron: 'chart-2',
    url: 'chart-2',
    json: 'chart-3',
  };
  const color = colorMap[type];
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-medium leading-none"
      style={{
        borderColor: `color-mix(in oklch, var(--${color}) 30%, transparent)`,
        background: `color-mix(in oklch, var(--${color}) 12%, transparent)`,
        color: `var(--${color})`,
      }}
    >
      {type}
    </span>
  );
}

/* ============ 主组件 ============ */

export function DynamicForm({
  fields,
  initialValues,
  secretsSet,
  prefix,
  onSubmit,
  submitLabel = '提交',
  onCancel,
  mode = 'create',
  className,
  isPending,
}: DynamicFormProps) {
  const safeFields = useMemo(() => fields ?? [], [fields]);
  const safeSecretsSet = useMemo(() => secretsSet ?? {}, [secretsSet]);
  const groups = useMemo(() => groupFields(safeFields), [safeFields]);

  const schema = useMemo(
    () => buildFormSchema(safeFields, mode, safeSecretsSet),
    [safeFields, mode, safeSecretsSet],
  );

  const defaults = useMemo(
    () => buildDefaults(safeFields, initialValues ?? {}),
    [safeFields, initialValues],
  );

  // 跟踪每个 secret 字段是否被 touched(用于 PATCH 时筛掉"未触碰"的 secret 字段)
  const [touchedSecrets, setTouchedSecrets] = useState<Record<string, boolean>>({});

  const form = useForm({
    resolver: zodResolver(schema) as Resolver<FieldValues>,
    defaultValues: defaults as FieldValues,
    mode: 'onBlur',
  });

  async function handleSubmit(values: FieldValues) {
    const out: Record<string, unknown> = {};
    for (const f of safeFields) {
      const v = values[f.key];
      // secret 字段:edit + 已配置 + 未 touched → 不提交(后端保留原值)
      if (f.type === 'secret' && mode === 'edit' && safeSecretsSet[f.key]) {
        if (!touchedSecrets[f.key]) continue;
        if (typeof v === 'string' && v.trim() === '') continue;
      }
      if (f.type === 'json') {
        if (typeof v === 'string' && v.trim()) {
          try {
            out[f.key] = JSON.parse(v);
          } catch {
            // 不应抵达(zod 已校验)
            continue;
          }
        } else if (f.required) {
          continue;
        }
      } else if (f.type === 'integer') {
        if (v === '' || v === undefined || v === null) {
          if (!f.required) continue;
          out[f.key] = null;
        } else {
          const n = Number(v);
          out[f.key] = Number.isNaN(n) ? v : n;
        }
      } else if (f.type === 'multiselect') {
        out[f.key] = Array.isArray(v) ? v : [];
      } else if (v === '' || v === undefined) {
        if (!f.required) continue;
      } else {
        out[f.key] = v;
      }
    }
    await onSubmit(out);
  }

  const submitting = isPending ?? form.formState.isSubmitting;

  return (
    <form
      onSubmit={form.handleSubmit(handleSubmit)}
      className={cn('flex flex-col gap-6', className)}
      noValidate
    >
      {prefix}

      {groups.map((group) => (
        <FormGroup
          key={group.name}
          name={group.name}
          fields={group.fields}
          control={form.control}
          secretsSet={safeSecretsSet}
          mode={mode}
          onSecretTouch={(key) =>
            setTouchedSecrets((prev) => (prev[key] ? prev : { ...prev, [key]: true }))
          }
        />
      ))}

      <div className="sticky bottom-0 -mx-6 flex flex-row-reverse items-center gap-2 border-t border-border bg-background/95 px-6 py-4 backdrop-blur">
        <Button type="submit" disabled={submitting}>
          {submitting ? (
            <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
          ) : null}
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
            取消
          </Button>
        ) : null}
      </div>
    </form>
  );
}

interface FormGroupProps {
  name: string;
  fields: ScriptField[];
  control: Control<FieldValues>;
  secretsSet: Record<string, boolean>;
  mode: 'create' | 'edit';
  onSecretTouch?: (key: string) => void;
}

function FormGroup({ name, fields, control, secretsSet, mode, onSecretTouch }: FormGroupProps) {
  const [open, setOpen] = useState(true);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-3">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between border-b border-border pb-1.5 text-left"
        >
          <span className="text-sm font-semibold text-foreground">{name}</span>
          <ChevronDown
            className={cn(
              'size-4 text-muted-foreground transition-transform',
              !open && '-rotate-90',
            )}
            strokeWidth={1.75}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-5">
        {fields.map((f) => (
          <FieldRenderer
            key={f.key}
            field={f}
            control={control}
            isSecretSet={!!secretsSet[f.key]}
            mode={mode}
            onSecretTouch={f.type === 'secret' ? () => onSecretTouch?.(f.key) : undefined}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default DynamicForm;
