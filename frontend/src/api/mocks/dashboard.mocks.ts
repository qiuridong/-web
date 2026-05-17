/**
 * Dashboard mock 数据 + TS 类型契约
 *
 * 字段名严格对齐 `进度/设计/后端架构.md` § 2.7 + § 1.3 / 1.4 / 1.2(scripts/instances/runs 字段)。
 * 后端 stub 阶段 hooks 在请求失败时 fallback 到这些 mock,使 UI 可用。
 *
 * TODO(Batch 3):后端真实接入后,这些类型应被 `import type { paths } from '@/api/schema'`
 * 自动生成的 schema 替换;mock 仅留给 storybook / tests。
 */

/* ===== Overview ===== */

export interface DashboardOverview {
  scripts: {
    total: number;
    enabled: number;
  };
  instances: {
    total: number;
    enabled: number;
    paused: number;
  };
  runs_24h: {
    total: number;
    success: number;
    failure: number;
    running: number;
  };
  success_rate_24h: number; // 0~1
  success_rate_7d: number; // 0~1
  /** sparkline 7 天每天执行成功率(0~1),前端展示用,后端可后续补 */
  sparkline_7d_success: number[];
  /** sparkline 7 天每天总执行次数,KPI "今日执行" 卡片用 */
  sparkline_7d_runs: number[];
  /** 24h 内通知发送条数,KPI 第 6 张卡片用 */
  notifications_24h: number;
  /** 下一次最早执行时间(ISO 8601),KPI "下次执行" 卡片用 */
  next_run_at: string | null;
}

export const mockOverview: DashboardOverview = {
  scripts: { total: 12, enabled: 11 },
  instances: { total: 18, enabled: 16, paused: 1 },
  runs_24h: { total: 148, success: 142, failure: 4, running: 2 },
  success_rate_24h: 0.964,
  success_rate_7d: 0.971,
  sparkline_7d_success: [0.95, 0.96, 0.98, 0.94, 0.97, 0.99, 0.964],
  sparkline_7d_runs: [132, 138, 145, 129, 152, 156, 148],
  notifications_24h: 23,
  next_run_at: new Date(Date.now() + 1000 * 60 * 18).toISOString(), // 18 分钟后
};

/* ===== Upcoming ===== */

export interface UpcomingItem {
  instance_id: number;
  instance_name: string;
  script_slug: string;
  script_name: string;
  next_run_at: string; // ISO
  cron_expr: string;
}

export const mockUpcoming: UpcomingItem[] = [
  {
    instance_id: 7,
    instance_name: 'coklw 主号',
    script_slug: 'coklw',
    script_name: 'coklw 每日签到',
    next_run_at: new Date(Date.now() + 1000 * 60 * 18).toISOString(),
    cron_expr: '0 9 * * *',
  },
  {
    instance_id: 3,
    instance_name: 'B 站 主号',
    script_slug: 'bilibili-daily',
    script_name: 'B 站每日签到',
    next_run_at: new Date(Date.now() + 1000 * 60 * 47).toISOString(),
    cron_expr: '0 8 * * *',
  },
  {
    instance_id: 9,
    instance_name: '微博 主号',
    script_slug: 'weibo-daily',
    script_name: '微博每日签到',
    next_run_at: new Date(Date.now() + 1000 * 60 * 92).toISOString(),
    cron_expr: '30 9 * * *',
  },
  {
    instance_id: 12,
    instance_name: 'V2EX 签到',
    script_slug: 'v2ex-daily',
    script_name: 'V2EX 每日签到',
    next_run_at: new Date(Date.now() + 1000 * 60 * 60 * 4).toISOString(),
    cron_expr: '0 13 * * *',
  },
  {
    instance_id: 14,
    instance_name: 'Acfun 签到',
    script_slug: 'acfun-daily',
    script_name: 'A 站每日签到',
    next_run_at: new Date(Date.now() + 1000 * 60 * 60 * 8).toISOString(),
    cron_expr: '0 17 * * *',
  },
];

/* ===== Recent failures ===== */

export interface RecentFailureItem {
  run_id: number;
  instance_id: number;
  instance_name: string;
  script_slug: string;
  script_name: string;
  status: 'failure' | 'error' | 'timeout';
  result_message: string | null;
  finished_at: string; // ISO
  duration_ms: number;
}

export const mockRecentFailures: RecentFailureItem[] = [
  {
    run_id: 9821,
    instance_id: 9,
    instance_name: '微博 主号',
    script_slug: 'weibo-daily',
    script_name: '微博每日签到',
    status: 'failure',
    result_message: 'Cookie 已失效,请重新提取',
    finished_at: new Date(Date.now() - 1000 * 60 * 122).toISOString(),
    duration_ms: 4231,
  },
  {
    run_id: 9803,
    instance_id: 14,
    instance_name: 'Acfun 签到',
    script_slug: 'acfun-daily',
    script_name: 'A 站每日签到',
    status: 'timeout',
    result_message: '执行超时(>120s)',
    finished_at: new Date(Date.now() - 1000 * 60 * 380).toISOString(),
    duration_ms: 120_000,
  },
  {
    run_id: 9787,
    instance_id: 3,
    instance_name: 'B 站 主号',
    script_slug: 'bilibili-daily',
    script_name: 'B 站每日签到',
    status: 'error',
    result_message: 'NetworkError: connect ECONNRESET',
    finished_at: new Date(Date.now() - 1000 * 60 * 600).toISOString(),
    duration_ms: 2310,
  },
];

/* ===== Timeline (recent runs) ===== */

export interface TimelineRow {
  run_id: number;
  timestamp: string; // ISO,= started_at
  script_slug: string;
  script_name: string;
  instance_id: number;
  instance_name: string;
  status: 'pending' | 'running' | 'success' | 'failure' | 'error' | 'timeout' | 'cancelled';
  duration_ms: number | null;
  trigger_type: 'manual' | 'scheduled' | 'retry' | 'api';
  /** stdout 摘要(前 200 字符)用于 hover 展开 */
  stdout_preview?: string;
  result_message?: string | null;
}

const now = Date.now();

export const mockTimeline: TimelineRow[] = [
  {
    run_id: 9842,
    timestamp: new Date(now - 1000 * 60 * 2).toISOString(),
    script_slug: 'coklw',
    script_name: 'coklw 每日签到',
    instance_id: 7,
    instance_name: 'coklw 主号',
    status: 'success',
    duration_ms: 1842,
    trigger_type: 'scheduled',
    stdout_preview: '[INFO] cookie 验证通过\n[INFO] 已签到,获得 +5 积分\n[INFO] 当前积分余额 1287',
    result_message: '签到成功,获得 5 积分',
  },
  {
    run_id: 9841,
    timestamp: new Date(now - 1000 * 60 * 12).toISOString(),
    script_slug: 'bilibili-daily',
    script_name: 'B 站每日签到',
    instance_id: 3,
    instance_name: 'B 站 主号',
    status: 'success',
    duration_ms: 8412,
    trigger_type: 'scheduled',
    stdout_preview: '[INFO] 完成投币 2 次\n[INFO] 完成观看 3 个视频\n[INFO] 完成分享',
    result_message: '所有任务完成',
  },
  {
    run_id: 9840,
    timestamp: new Date(now - 1000 * 60 * 35).toISOString(),
    script_slug: 'v2ex-daily',
    script_name: 'V2EX 每日签到',
    instance_id: 12,
    instance_name: 'V2EX 签到',
    status: 'success',
    duration_ms: 612,
    trigger_type: 'scheduled',
    result_message: '签到成功',
  },
  {
    run_id: 9839,
    timestamp: new Date(now - 1000 * 60 * 60).toISOString(),
    script_slug: 'coklw',
    script_name: 'coklw 每日签到',
    instance_id: 8,
    instance_name: 'coklw 备用号',
    status: 'success',
    duration_ms: 1923,
    trigger_type: 'manual',
    result_message: '签到成功,获得 5 积分',
  },
  {
    run_id: 9838,
    timestamp: new Date(now - 1000 * 60 * 122).toISOString(),
    script_slug: 'weibo-daily',
    script_name: '微博每日签到',
    instance_id: 9,
    instance_name: '微博 主号',
    status: 'failure',
    duration_ms: 4231,
    trigger_type: 'scheduled',
    stdout_preview: '[ERROR] Cookie 已失效,HTTP 302 → /login',
    result_message: 'Cookie 已失效,请重新提取',
  },
  {
    run_id: 9837,
    timestamp: new Date(now - 1000 * 60 * 180).toISOString(),
    script_slug: 'bilibili-daily',
    script_name: 'B 站每日签到',
    instance_id: 4,
    instance_name: 'B 站 小号',
    status: 'success',
    duration_ms: 7823,
    trigger_type: 'scheduled',
  },
  {
    run_id: 9836,
    timestamp: new Date(now - 1000 * 60 * 240).toISOString(),
    script_slug: 'acfun-daily',
    script_name: 'A 站每日签到',
    instance_id: 14,
    instance_name: 'Acfun 签到',
    status: 'timeout',
    duration_ms: 120_000,
    trigger_type: 'scheduled',
    stdout_preview: '[INFO] 开始登录\n[INFO] 等待 turnstile 验证 ...\n(无后续输出)',
    result_message: '执行超时(>120s)',
  },
  {
    run_id: 9835,
    timestamp: new Date(now - 1000 * 60 * 360).toISOString(),
    script_slug: 'coklw',
    script_name: 'coklw 每日签到',
    instance_id: 7,
    instance_name: 'coklw 主号',
    status: 'success',
    duration_ms: 1789,
    trigger_type: 'scheduled',
    result_message: '签到成功,获得 5 积分',
  },
  {
    run_id: 9834,
    timestamp: new Date(now - 1000 * 60 * 600).toISOString(),
    script_slug: 'bilibili-daily',
    script_name: 'B 站每日签到',
    instance_id: 3,
    instance_name: 'B 站 主号',
    status: 'error',
    duration_ms: 2310,
    trigger_type: 'scheduled',
    stdout_preview: '[ERROR] connect ECONNRESET 192.0.2.1:443',
    result_message: 'NetworkError: connect ECONNRESET',
  },
  {
    run_id: 9833,
    timestamp: new Date(now - 1000 * 60 * 720).toISOString(),
    script_slug: 'v2ex-daily',
    script_name: 'V2EX 每日签到',
    instance_id: 12,
    instance_name: 'V2EX 签到',
    status: 'success',
    duration_ms: 581,
    trigger_type: 'scheduled',
    result_message: '签到成功',
  },
];
