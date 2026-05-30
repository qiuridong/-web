/**
 * 通知预设 — apprise 渠道 URL 模板 + Jinja2 通知模板。
 *
 * 用途:
 *   - ChannelSheet 渠道类型下拉,选中后回填 apprise_url 输入框
 *   - RuleSheet 模板预设下拉,选中后回填 template textarea
 *
 * apprise URL 参考: https://github.com/caronc/apprise/wiki
 * 模板字段速查: backend/app/notifications/templates.py
 */

// ============================================================
// 渠道 URL 预设
// ============================================================
export interface ChannelPreset {
  /** 唯一 ID(不会被持久化,只用于下拉选中态) */
  id: string;
  /** 显示名 */
  label: string;
  /** apprise URL 模板,占位用大写中文/英文便于直接看出该填啥 */
  urlTemplate: string;
  /** 一句话说明 + 凭证哪里拿 */
  helper: string;
}

export const CHANNEL_PRESETS: ChannelPreset[] = [
  {
    id: 'qq-email',
    label: 'QQ 邮箱',
    urlTemplate: 'mailtos://你的QQ号:授权码@qq.com?to=收件邮箱@qq.com',
    helper:
      '授权码:登录 QQ 邮箱 → 设置 → 账户 → 开启「POP3/SMTP」服务,生成 16 位授权码(不是 QQ 密码)。to= 后填收件人,可与发件人同账号。',
  },
  {
    id: 'gmail',
    label: 'Gmail',
    urlTemplate: 'mailtos://你的Gmail:应用密码@gmail.com?to=收件邮箱@gmail.com',
    helper:
      '需先在 Google 账户开启两步验证,再「应用密码」生成 16 位密码(不是登录密码)。',
  },
  {
    id: 'outlook',
    label: 'Outlook / Hotmail',
    urlTemplate: 'mailtos://你的邮箱:密码@outlook.com?to=收件邮箱@outlook.com',
    helper:
      '若账号开启了两步验证,需在「安全 → 应用密码」生成专用密码。',
  },
  {
    id: 'telegram',
    label: 'Telegram Bot',
    urlTemplate: 'tgram://BOT_TOKEN/CHAT_ID',
    helper:
      'BOT_TOKEN:@BotFather 发 /newbot 创建。CHAT_ID:给 @userinfobot 发任意消息获取(私聊用正数,群组用负数)。',
  },
  {
    id: 'bark',
    label: 'Bark(iOS 推送)',
    urlTemplate: 'barks://api.day.app/你的KEY',
    helper:
      'iOS 端在 Bark App 顶部「设备」中复制 KEY。barks:// 走 HTTPS,bark:// 走 HTTP。',
  },
  {
    id: 'dingtalk',
    label: '钉钉群机器人',
    urlTemplate: 'dingtalk://ACCESS_TOKEN/SECRET',
    helper:
      'ACCESS_TOKEN:Webhook URL 中 access_token=xxx 的部分。SECRET:开启「加签」后的 SEC 密钥(必填,不开加签机器人会被钉钉拒)。',
  },
  {
    id: 'lark',
    label: '飞书群机器人',
    urlTemplate: 'lark://HOOK_TOKEN',
    helper:
      'HOOK_TOKEN:群机器人 webhook URL 末段(/hook/ 后面那串 UUID)。若开了「签名校验」需追加 ?secret=SIGN_SECRET。',
  },
  {
    id: 'wechat-work',
    label: '企业微信(自建机器人)',
    urlTemplate: 'wxteams://WEBHOOK_KEY',
    helper:
      'WEBHOOK_KEY:群机器人 webhook URL 中 key=xxx 的部分(纯 UUID)。',
  },
  {
    id: 'discord',
    label: 'Discord',
    urlTemplate: 'discord://WEBHOOK_ID/WEBHOOK_TOKEN',
    helper:
      '频道设置 → 整合 → Webhook → 复制 URL,格式 https://discord.com/api/webhooks/<WEBHOOK_ID>/<WEBHOOK_TOKEN>。',
  },
  {
    id: 'slack',
    label: 'Slack',
    urlTemplate: 'slack://TOKEN_A/TOKEN_B/TOKEN_C',
    helper:
      'Slack App incoming webhook URL 末段 /services/T.../B.../xxx 的三段。',
  },
  {
    id: 'serverchan',
    label: 'Server 酱(微信)',
    urlTemplate: 'tcoms://SENDKEY',
    helper:
      'Server 酱 Turbo:在 https://sct.ftqq.com 获取 SENDKEY(SCTxxxxx)。',
  },
  {
    id: 'pushover',
    label: 'Pushover',
    urlTemplate: 'pover://USER_KEY@APP_TOKEN',
    helper:
      'USER_KEY:Pushover 主页右上角。APP_TOKEN:在 https://pushover.net/apps/build 创建应用获取。',
  },
  {
    id: 'webhook-json',
    label: '通用 Webhook(POST JSON)',
    urlTemplate: 'jsons://HOST:PORT/PATH',
    helper:
      '把通知 POST 成 JSON 到任意 HTTP 端点。jsons:// 为 HTTPS,json:// 为 HTTP。',
  },
  {
    id: 'custom',
    label: '自定义(空白)',
    urlTemplate: '',
    helper: '清空输入框,自行填写 apprise URL。',
  },
];

// ============================================================
// 通知模板预设(Jinja2)
// ============================================================
export interface TemplatePreset {
  id: string;
  label: string;
  /** 完整模板内容(可含 `---` 分隔 title / body) */
  content: string;
  /** 用法说明 */
  description: string;
}

export const TEMPLATE_PRESETS: TemplatePreset[] = [
  {
    id: 'default',
    label: '默认(留空,使用内置模板)',
    content: '',
    description:
      '不写自定义模板时使用系统默认:标题 [EVENT] 实例 - 脚本 / 正文含状态+耗时+stderr 尾部 20 行。',
  },
  {
    id: 'simple',
    label: '简洁版(短消息渠道)',
    content: `[{{ event | upper }}] {{ script.name }} · {{ instance.name }}
---
🕐 {{ run.finished_at | local_time }}
⏱  {{ run.duration_ms | human_duration }}
📝 {{ run.result_message or '(无消息)' }}`,
    description:
      '1 行标题 + 3 行正文,适合 Telegram / QQ 邮箱主题等显示空间有限的场景。',
  },
  {
    id: 'diagnostic',
    label: '完整诊断版(失败排查推荐)',
    content: `❌ [{{ event | upper }}] {{ script.name }} / {{ instance.name }}
---
脚本: {{ script.name }} v{{ script.version }}
实例: {{ instance.name }}{% if instance.cron_expr %} ({{ instance.cron_expr }}){% endif %}
状态: {{ run.status }} (exit={{ run.exit_code }})
开始: {{ run.started_at | local_time }}
结束: {{ run.finished_at | local_time }}
耗时: {{ run.duration_ms | human_duration }}
节点: {{ run.host or 'local' }}
触发: {{ run.trigger_type }}

—— 结果 ——
{{ run.result_message or '(无消息)' }}

{% if run.stderr %}
—— stderr 尾部 ——
{{ run.stderr | tail(20) }}
{% endif %}
{% if run.stdout %}
—— stdout 尾部 ——
{{ run.stdout | tail(30) }}
{% endif %}`,
    description:
      '推荐用于「失败 / 错误 / 超时」事件;含完整诊断信息,方便排查问题。',
  },
  {
    id: 'markdown',
    label: 'Markdown 富文本(TG / Slack / Discord)',
    content: `**{{ event | upper }}** · \`{{ script.slug }}\`
---
**实例**: \`{{ instance.name }}\`
**状态**: \`{{ run.status }}\` (exit \`{{ run.exit_code }}\`)
**耗时**: {{ run.duration_ms | human_duration }}
**时间**: {{ run.finished_at | local_time }}

> {{ run.result_message or '(无消息)' }}

\`\`\`
{{ run.stdout | tail(15) }}
\`\`\``,
    description:
      'Markdown 富文本,适合支持 Markdown 渲染的频道。',
  },
  {
    id: 'success-brief',
    label: '成功简报(每日 OK 推送)',
    content: `✅ {{ script.name }} · {{ instance.name }} OK
---
{{ run.finished_at | local_time }} 完成,耗时 {{ run.duration_ms | human_duration }}
{% if run.result_message %}{{ run.result_message }}{% endif %}`,
    description: '只在「成功」事件触发时用,告诉你今天还活着即可。',
  },
  {
    id: 'node-offline',
    label: '🔌 节点掉线告警(配合「节点掉线」事件)',
    content: `⚠️ 节点掉线: {{ node.name or node.slug }}
---
节点 **{{ node.name or node.slug }}** (\`{{ node.slug }}\`) 已离线。
最后心跳: {{ node.last_seen_at | local_time }}
请检查该 VPS 上 signin-agent 是否在运行。`,
    description:
      '仅用于「节点掉线」事件(作用域固定全局)。可用字段:node.slug / node.name / node.last_seen_at / node.version。留空也行,系统有内置默认模板。',
  },
];

// ============================================================
// 字段速查(模板可用变量与 filter)
// ============================================================
export interface FieldGroup {
  label: string;
  /** 字段名(含 {{ }} 包裹便于直接复制) */
  fields: { name: string; note?: string }[];
}

export const TEMPLATE_FIELD_GROUPS: FieldGroup[] = [
  {
    label: '事件',
    fields: [
      { name: '{{ event }}', note: 'success / failure / error / timeout / any / node_offline' },
    ],
  },
  {
    label: '脚本(script)',
    fields: [
      { name: '{{ script.slug }}', note: '唯一标识,如 jmcomic' },
      { name: '{{ script.name }}', note: '显示名' },
      { name: '{{ script.version }}', note: '如 1.2.0' },
      { name: '{{ script.description }}' },
      { name: '{{ script.author }}' },
      { name: '{{ script.homepage }}' },
    ],
  },
  {
    label: '实例(instance)',
    fields: [
      { name: '{{ instance.id }}' },
      { name: '{{ instance.name }}', note: '实例名,如「我的账号」' },
      { name: '{{ instance.description }}' },
      { name: '{{ instance.cron_expr }}', note: 'cron 表达式' },
      { name: '{{ instance.timeout_sec }}' },
      { name: '{{ instance.enabled }}' },
    ],
  },
  {
    label: '运行(run)',
    fields: [
      { name: '{{ run.id }}' },
      { name: '{{ run.status }}', note: 'success / failure / error / timeout' },
      { name: '{{ run.exit_code }}' },
      { name: '{{ run.started_at }}', note: 'ISO 字符串,搭配 local_time 用' },
      { name: '{{ run.finished_at }}' },
      { name: '{{ run.duration_ms }}', note: '毫秒,搭配 human_duration 用' },
      { name: '{{ run.result_message }}', note: '脚本返回的 message' },
      { name: '{{ run.stdout }}', note: '完整 stdout,搭配 tail(N) 用' },
      { name: '{{ run.stderr }}' },
      { name: '{{ run.trigger_type }}', note: 'manual / scheduled / retry' },
      { name: '{{ run.host }}', note: '节点名,如 local / vps-jm' },
    ],
  },
  {
    label: '节点(node — 仅「节点掉线」事件)',
    fields: [
      { name: '{{ node.slug }}', note: '节点唯一标识,如 vps-jm' },
      { name: '{{ node.name }}', note: '节点显示名' },
      { name: '{{ node.last_seen_at }}', note: '最后心跳 ISO,搭配 local_time' },
      { name: '{{ node.version }}', note: 'agent 版本' },
    ],
  },
  {
    label: '自定义 filter(用 |  接)',
    fields: [
      { name: '| tail(20)', note: '取尾部 N 行,常用于 stdout/stderr' },
      { name: '| human_duration', note: 'ms → "1m 23s"' },
      { name: '| local_time', note: 'ISO → 北京时间 "2026-05-24 12:34:56"' },
      {
        name: '| local_time("Asia/Tokyo", "%Y-%m-%d")',
        note: '指定时区 + 格式',
      },
      { name: '| upper / | lower', note: 'jinja 内置' },
      { name: 'or "默认值"', note: '空时用默认,如 run.result_message or "(无)"' },
    ],
  },
];

// ============================================================
// 模板分隔约定提示(供 UI 直接展示)
// ============================================================
export const TEMPLATE_FORMAT_NOTE =
  '格式:留空 = 用默认;包含一行 `---` = 上半为标题/下半为正文;否则整段当正文,标题走默认。';
