/**
 * <InstanceFormSheet> — 创建 / 编辑实例的右抽屉表单
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.5、§ 3.6。
 *
 * 用法:
 *   <InstanceFormSheet
 *     open={open}
 *     onOpenChange={setOpen}
 *     mode="create" | "edit"
 *     script={script}                   // 提供 fields_schema / slug / default_cron / default_timeout_sec
 *     instance={instance | undefined}    // edit 时提供
 *   />
 *
 * 行为:
 *   - 顶部:实例元信息(name / description / cron_expr / timeout_sec / max_retries / retry_interval_sec)
 *   - 下方:DynamicForm 渲染 script.fields_schema(用户配置 dict)
 *   - 提交:create → POST /instances;edit → PATCH /instances/{id}
 *   - 关闭:无 dirty 直接关;有 dirty 弹 confirm(简化:暂用 confirm 原生)
 */
import { useEffect, useMemo, useState } from 'react';

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import CronInput from '@/components/common/CronInput';
import DynamicForm from '@/components/common/DynamicForm';

import {
  useCreateInstance,
  useUpdateInstance,
  type InstanceDetail,
  type InstanceCreatePayload,
  type InstanceUpdatePayload,
} from '@/api/hooks/instances';
import type { ScriptDetail } from '@/api/hooks/scripts';
import { cn } from '@/lib/utils';

export interface InstanceFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: 'create' | 'edit';
  script: ScriptDetail;
  /** edit 模式必填 */
  instance?: InstanceDetail;
}

interface MetaFields {
  name: string;
  description?: string;
  cron_expr?: string;
  timeout_sec?: string;
  max_retries?: string;
  retry_interval_sec?: string;
}

export function InstanceFormSheet({
  open,
  onOpenChange,
  mode,
  script,
  instance,
}: InstanceFormSheetProps) {
  const create = useCreateInstance();
  const update = useUpdateInstance();

  const isEdit = mode === 'edit';
  const submitting = create.isPending || update.isPending;

  // 元信息(实例自身字段,与 fields_schema 分开)
  const initialMeta: MetaFields = useMemo(
    () => ({
      name: instance?.name ?? '',
      description: instance?.description ?? '',
      cron_expr: instance?.cron_expr ?? script.default_cron ?? '',
      timeout_sec:
        instance?.timeout_sec !== undefined && instance?.timeout_sec !== null
          ? String(instance.timeout_sec)
          : script.default_timeout_sec
            ? String(script.default_timeout_sec)
            : '',
      max_retries:
        instance?.max_retries !== undefined ? String(instance.max_retries) : '0',
      retry_interval_sec:
        instance?.retry_interval_sec !== undefined
          ? String(instance.retry_interval_sec)
          : '60',
    }),
    [instance, script.default_cron, script.default_timeout_sec],
  );

  const [meta, setMeta] = useState<MetaFields>(initialMeta);

  useEffect(() => {
    // 开抽屉时重置元信息(切换 instance 也重置)
    if (open) setMeta(initialMeta);
  }, [open, initialMeta]);

  function patchMeta(p: Partial<MetaFields>) {
    setMeta((s) => ({ ...s, ...p }));
  }

  async function handleSubmit(config: Record<string, unknown>) {
    // 拼装实例 payload
    const timeoutNum = meta.timeout_sec ? Number(meta.timeout_sec) : undefined;
    const maxRetriesNum = meta.max_retries ? Number(meta.max_retries) : 0;
    const retryIntervalNum = meta.retry_interval_sec
      ? Number(meta.retry_interval_sec)
      : 60;

    if (isEdit && instance) {
      const payload: InstanceUpdatePayload = {
        name: meta.name,
        description: meta.description || undefined,
        cron_expr: meta.cron_expr || undefined,
        timeout_sec: timeoutNum && !Number.isNaN(timeoutNum) ? timeoutNum : undefined,
        max_retries: Number.isFinite(maxRetriesNum) ? maxRetriesNum : 0,
        retry_interval_sec: Number.isFinite(retryIntervalNum) ? retryIntervalNum : 60,
        config,
      };
      await update.mutateAsync({ id: instance.id, payload, scriptSlug: script.slug });
    } else {
      const payload: InstanceCreatePayload = {
        script_slug: script.slug,
        name: meta.name,
        description: meta.description || undefined,
        cron_expr: meta.cron_expr || undefined,
        timeout_sec: timeoutNum && !Number.isNaN(timeoutNum) ? timeoutNum : undefined,
        max_retries: Number.isFinite(maxRetriesNum) ? maxRetriesNum : 0,
        retry_interval_sec: Number.isFinite(retryIntervalNum) ? retryIntervalNum : 60,
        config,
      };
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  }

  const initialValues = useMemo(() => instance?.config ?? {}, [instance]);
  const secretsSet = useMemo(() => instance?._secret_set ?? {}, [instance]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn(
          'flex w-full flex-col gap-0 overflow-hidden p-0',
          'sm:max-w-2xl',
        )}
      >
        <SheetHeader className="border-b border-border px-6 py-4">
          <SheetTitle>
            {isEdit ? `编辑实例 - ${instance?.name ?? ''}` : '新建实例'}
          </SheetTitle>
          <SheetDescription>
            脚本:{script.name} ({script.slug}) · v{script.version}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <DynamicForm
            fields={script.fields_schema}
            initialValues={initialValues}
            secretsSet={secretsSet}
            mode={mode}
            isPending={submitting}
            submitLabel={isEdit ? '保存修改' : '创建实例'}
            onCancel={() => onOpenChange(false)}
            onSubmit={handleSubmit}
            prefix={
              <div className="space-y-5 border-b border-border pb-6">
                <h3 className="text-sm font-semibold text-foreground">实例元信息</h3>
                <div className="space-y-1.5">
                  <Label htmlFor="meta-name">
                    实例名
                    <span className="ml-0.5 text-danger">*</span>
                  </Label>
                  <Input
                    id="meta-name"
                    value={meta.name}
                    onChange={(e) => patchMeta({ name: e.target.value })}
                    placeholder="如 B站-主号"
                    required
                    className="h-10"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="meta-desc">备注</Label>
                  <Textarea
                    id="meta-desc"
                    rows={2}
                    value={meta.description ?? ''}
                    onChange={(e) => patchMeta({ description: e.target.value })}
                    placeholder="可选,自己看的备注"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="meta-cron">cron 表达式</Label>
                  <CronInput
                    id="meta-cron"
                    value={meta.cron_expr ?? ''}
                    onChange={(v) => patchMeta({ cron_expr: v })}
                    placeholder={script.default_cron ?? '例如 0 9 * * *'}
                  />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="meta-timeout">超时(秒)</Label>
                    <Input
                      id="meta-timeout"
                      type="number"
                      min={1}
                      max={3600}
                      value={meta.timeout_sec ?? ''}
                      onChange={(e) => patchMeta({ timeout_sec: e.target.value })}
                      placeholder={
                        script.default_timeout_sec
                          ? String(script.default_timeout_sec)
                          : '300'
                      }
                      className="h-10 tabular-nums"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="meta-retries">失败重试次数</Label>
                    <Input
                      id="meta-retries"
                      type="number"
                      min={0}
                      max={10}
                      value={meta.max_retries ?? '0'}
                      onChange={(e) => patchMeta({ max_retries: e.target.value })}
                      className="h-10 tabular-nums"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="meta-retry-interval">首次重试等待(秒)</Label>
                    <Input
                      id="meta-retry-interval"
                      type="number"
                      min={5}
                      max={3600}
                      value={meta.retry_interval_sec ?? '60'}
                      onChange={(e) =>
                        patchMeta({ retry_interval_sec: e.target.value })
                      }
                      className="h-10 tabular-nums"
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  以下为脚本声明字段,按 manifest 渲染。secret 字段在编辑模式留空则保持原值。
                </p>
              </div>
            }
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default InstanceFormSheet;
