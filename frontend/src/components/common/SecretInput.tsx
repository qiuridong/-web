/**
 * <SecretInput> — 敏感字段输入
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.6、§ 4。
 *
 * 行为:
 *   - 默认 type=password,显隐切换按钮(eye / eye-off)
 *   - 复制按钮:仅显示模式可点
 *   - isSet && !touched 时占位 "********(已配置,留空保持不变)"
 *   - 用户开始输入即视为 touched;PATCH 时若 touched 但 value 仍 empty,DynamicForm 不发送此字段
 *
 * 注意:
 *   - 该组件本身不处理"该字段是否提交"的逻辑(由调用方/DynamicForm 决定);
 *     只暴露 onChange + onTouched + 渲染样式
 */
import { forwardRef, useId, useState, type ChangeEvent } from 'react';
import { Copy, Eye, EyeOff, Lock } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface SecretInputProps {
  name?: string;
  placeholder?: string;
  value?: string;
  defaultValue?: string;
  /** 服务端 _secret_set 给出的"该字段已存值" */
  isSet?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  className?: string;
  /** 触发时机:onChange(每次按键) */
  onChange?: (next: string) => void;
  /** 用户首次开始输入时回调,父组件用以标记 touched(决定 PATCH 时是否提交此字段) */
  onTouched?: () => void;
  /** 提供 react-hook-form 的 onBlur(可选) */
  onBlur?: () => void;
  id?: string;
  /** 是否允许通过复制按钮一键复制(默认 true;只在显示模式 + 有内容时可点) */
  allowCopy?: boolean;
  /** 标识使用场景:'create' 时不会出现 "已配置,留空保持不变" 占位 */
  mode?: 'create' | 'edit';
}

export const SecretInput = forwardRef<HTMLInputElement, SecretInputProps>(function SecretInput(
  {
    name,
    placeholder,
    value,
    defaultValue,
    isSet = false,
    disabled,
    readOnly,
    className,
    onChange,
    onTouched,
    onBlur,
    id,
    allowCopy = true,
    mode = 'edit',
  },
  ref,
) {
  const reactId = useId();
  const inputId = id ?? `secret-${reactId}`;
  const [showText, setShowText] = useState(false);
  const [internalTouched, setInternalTouched] = useState(false);

  const displayValue = value;
  const isEditMode = mode === 'edit';
  const showPlaceholder = isEditMode && isSet && !internalTouched;

  const finalPlaceholder = showPlaceholder
    ? '已配置,留空保持不变'
    : (placeholder ?? '');

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    if (!internalTouched) {
      setInternalTouched(true);
      onTouched?.();
    }
    onChange?.(e.target.value);
  }

  async function handleCopy() {
    if (!displayValue) {
      toast.info('当前无可复制内容');
      return;
    }
    try {
      await navigator.clipboard.writeText(displayValue);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
    }
  }

  return (
    <div className={cn('relative flex w-full items-center', className)}>
      <span
        className="pointer-events-none absolute left-3 text-muted-foreground/60"
        aria-hidden
      >
        <Lock className="size-3.5" strokeWidth={1.75} />
      </span>
      <Input
        ref={ref}
        id={inputId}
        name={name}
        type={showText ? 'text' : 'password'}
        autoComplete="new-password"
        spellCheck={false}
        value={displayValue}
        defaultValue={defaultValue}
        placeholder={finalPlaceholder}
        disabled={disabled}
        readOnly={readOnly}
        onChange={handleChange}
        onBlur={onBlur}
        className={cn(
          'h-10 pl-8 pr-20 font-mono text-sm',
          showPlaceholder && 'placeholder:text-muted-foreground/80 placeholder:italic',
        )}
        aria-describedby={isSet ? `${inputId}-hint` : undefined}
      />
      <div className="absolute right-1.5 flex items-center gap-0.5">
        {allowCopy && showText ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="size-7 p-0 text-muted-foreground hover:text-foreground"
            onClick={handleCopy}
            disabled={disabled || !displayValue}
            aria-label="复制"
            title="复制"
          >
            <Copy className="size-3.5" strokeWidth={1.75} />
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="size-7 p-0 text-muted-foreground hover:text-foreground"
          onClick={() => setShowText((s) => !s)}
          disabled={disabled}
          aria-label={showText ? '隐藏' : '显示'}
          aria-pressed={showText}
          title={showText ? '隐藏' : '显示'}
        >
          {showText ? (
            <EyeOff className="size-3.5" strokeWidth={1.75} />
          ) : (
            <Eye className="size-3.5" strokeWidth={1.75} />
          )}
        </Button>
      </div>
    </div>
  );
});

export default SecretInput;
