/**
 * <RunsPanel> — 执行历史 Tab(脚本详情 + /runs 通用)
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.7。
 *
 * 接 useRuns(filter),DataTable 展示;点击行打开 RunDetailSheet。
 */
import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Activity, History, RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import DataTable from '@/components/common/DataTable';
import EmptyState from '@/components/common/EmptyState';
import RunDetailSheet from '@/components/common/RunDetailSheet';
import StatusBadge, { type Status } from '@/components/common/StatusBadge';

import { useRuns, type RunListItem, type RunsFilter } from '@/api/hooks/runs';
import { formatDate, formatDuration, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface RunsPanelProps {
  filter?: RunsFilter;
  className?: string;
}

function runStatusToBadge(s?: string | null): Status {
  switch (s) {
    case 'success':
      return 'success';
    case 'failure':
    case 'error':
    case 'timeout':
    case 'cancelled':
      return 'failure';
    case 'running':
      return 'running';
    case 'pending':
      return 'pending';
    default:
      return 'unknown';
  }
}

export function RunsPanel({ filter = {}, className }: RunsPanelProps) {
  const [selected, setSelected] = useState<number | undefined>(undefined);
  const { data: runs, isLoading, isFetching, refetch } = useRuns({
    page_size: 50,
    ...filter,
  });

  const columns = useMemo<ColumnDef<RunListItem>[]>(
    () => [
      {
        id: 'status',
        accessorKey: 'status',
        header: '状态',
        cell: ({ row }) => (
          <StatusBadge
            status={runStatusToBadge(row.original.status)}
            label={row.original.status}
          />
        ),
      },
      {
        accessorKey: 'started_at',
        header: '开始时间',
        cell: ({ getValue }) => {
          const v = getValue() as string;
          return (
            <span className="tabular-nums text-xs" title={formatDate(v)}>
              {formatRelative(v)}
            </span>
          );
        },
      },
      {
        id: 'instance',
        header: '实例 / 脚本',
        cell: ({ row }) => {
          const r = row.original;
          const instName = r.instance?.name ?? `#${r.instance_id}`;
          return (
            <div className="min-w-0">
              <div className="truncate text-sm">{instName}</div>
              <div className="truncate font-mono text-[11px] text-muted-foreground">
                {r.script_slug}
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: 'duration_ms',
        header: '时长',
        cell: ({ getValue }) => (
          <span className="tabular-nums text-xs">
            {formatDuration((getValue() as number) ?? null)}
          </span>
        ),
      },
      {
        accessorKey: 'trigger_type',
        header: '触发',
        cell: ({ getValue }) => (
          <Badge variant="outline" className="font-mono text-[11px]">
            {(getValue() as string) ?? '—'}
          </Badge>
        ),
      },
      {
        accessorKey: 'exit_code',
        header: 'exit',
        cell: ({ getValue }) => {
          const v = getValue() as number | null;
          return (
            <code className="font-mono text-xs">{v !== null && v !== undefined ? v : '—'}</code>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          {runs && runs.length > 0
            ? `共 ${runs.length} 条记录`
            : '尚无执行记录'}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={cn('size-4', isFetching && 'animate-spin')} strokeWidth={1.75} />
          <span className="ml-1.5 hidden sm:inline">刷新</span>
        </Button>
      </div>

      <DataTable<RunListItem, unknown>
        columns={columns}
        data={runs ?? []}
        loading={isLoading}
        onRowClick={(row) => setSelected(row.id)}
        empty={
          <EmptyState
            icon={History}
            title="尚无执行历史"
            description="实例触发执行后,记录会出现在这里"
            action={
              <Badge variant="outline" className="gap-1">
                <Activity className="size-3" strokeWidth={1.75} />
                可在"实例"Tab 中点击「立即运行」
              </Badge>
            }
          />
        }
        getRowId={(row) => String((row as RunListItem).id)}
        hideColumnVisibility
      />

      <RunDetailSheet
        runId={selected}
        open={selected !== undefined}
        onOpenChange={(open) => !open && setSelected(undefined)}
      />
    </div>
  );
}

export default RunsPanel;
