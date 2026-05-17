/**
 * Scripts mock 数据 + TS 类型契约
 *
 * 字段名严格对齐 `进度/设计/后端架构.md` § 1.2(scripts 表) + § 1.3(instances 冗余字段)。
 * 后端 stub 阶段 hooks 在请求失败时 fallback 到这些 mock。
 *
 * 这里的"卡片用 ScriptListItem"是 UI 视角的扁平结构(脚本基本信息 + 实例汇总 + 上次执行摘要),
 * 真实接入时可由 `/api/v1/scripts?include=stats` 返回,或前端聚合多个端点。
 *
 * TODO(Batch 3):接入 `/api/v1/scripts` + `/api/v1/instances?script_id=...` 后,
 * 由 hook 内部组合,不再走 mock。
 */

export interface ScriptListItem {
  /** 后端 DB 主键(后端响应必带;mock 数据缺省) */
  id?: number;
  slug: string;
  name: string;
  description: string | null;
  version: string;
  author: string | null;
  homepage: string | null;
  default_cron: string | null;
  enabled: boolean;
  requires_secret: boolean;
  /** 该脚本下的实例数(汇总) */
  instance_count: number;
  /** 启用中的实例数 */
  instance_enabled_count: number;
  /** 最近一次执行状态(任意实例);用于卡片 status dot */
  last_run_status: 'success' | 'failure' | 'error' | 'timeout' | 'pending' | 'running' | null;
  last_run_at: string | null;
  next_run_at: string | null;
  /** 7 天成功率,卡片次行展示 */
  success_rate_7d: number | null;
}

export const mockScripts: ScriptListItem[] = [
  {
    slug: 'coklw',
    name: 'coklw 每日签到',
    description: 'WordPress 站点 coklw.net 每日签到,获得积分',
    version: '1.0.0',
    author: 'yunkelai',
    homepage: 'https://coklw.net',
    default_cron: '0 9 * * *',
    enabled: true,
    requires_secret: true,
    instance_count: 2,
    instance_enabled_count: 2,
    last_run_status: 'success',
    last_run_at: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
    next_run_at: new Date(Date.now() + 1000 * 60 * 18).toISOString(),
    success_rate_7d: 1.0,
  },
  {
    slug: 'bilibili-daily',
    name: 'B 站每日签到',
    description: '自动完成 B 站每日登录、看视频、投币、分享任务',
    version: '1.2.0',
    author: 'yunkelai',
    homepage: 'https://bilibili.com',
    default_cron: '0 8 * * *',
    enabled: true,
    requires_secret: true,
    instance_count: 2,
    instance_enabled_count: 2,
    last_run_status: 'error',
    last_run_at: new Date(Date.now() - 1000 * 60 * 600).toISOString(),
    next_run_at: new Date(Date.now() + 1000 * 60 * 47).toISOString(),
    success_rate_7d: 0.93,
  },
  {
    slug: 'weibo-daily',
    name: '微博每日签到',
    description: '微博超话签到与每日任务',
    version: '0.9.0',
    author: 'yunkelai',
    homepage: null,
    default_cron: '30 9 * * *',
    enabled: true,
    requires_secret: true,
    instance_count: 1,
    instance_enabled_count: 1,
    last_run_status: 'failure',
    last_run_at: new Date(Date.now() - 1000 * 60 * 122).toISOString(),
    next_run_at: new Date(Date.now() + 1000 * 60 * 92).toISOString(),
    success_rate_7d: 0.62,
  },
  {
    slug: 'v2ex-daily',
    name: 'V2EX 每日签到',
    description: 'V2EX 论坛每日签到领铜币',
    version: '1.0.0',
    author: 'yunkelai',
    homepage: 'https://v2ex.com',
    default_cron: '0 13 * * *',
    enabled: true,
    requires_secret: false,
    instance_count: 1,
    instance_enabled_count: 1,
    last_run_status: 'success',
    last_run_at: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
    next_run_at: new Date(Date.now() + 1000 * 60 * 60 * 4).toISOString(),
    success_rate_7d: 1.0,
  },
  {
    slug: 'acfun-daily',
    name: 'A 站每日签到',
    description: 'AcFun 弹幕视频网每日签到',
    version: '0.5.0',
    author: 'yunkelai',
    homepage: 'https://acfun.cn',
    default_cron: '0 17 * * *',
    enabled: true,
    requires_secret: true,
    instance_count: 1,
    instance_enabled_count: 1,
    last_run_status: 'timeout',
    last_run_at: new Date(Date.now() - 1000 * 60 * 380).toISOString(),
    next_run_at: new Date(Date.now() + 1000 * 60 * 60 * 8).toISOString(),
    success_rate_7d: 0.71,
  },
  {
    slug: 'douban-daily',
    name: '豆瓣每日签到',
    description: '豆瓣读书与电影日常打卡',
    version: '0.3.0',
    author: 'yunkelai',
    homepage: 'https://douban.com',
    default_cron: '0 10 * * *',
    enabled: false,
    requires_secret: true,
    instance_count: 0,
    instance_enabled_count: 0,
    last_run_status: null,
    last_run_at: null,
    next_run_at: null,
    success_rate_7d: null,
  },
];
