---
tags: [签到管家, 速查, 规范, manifest, 脚本开发]
created: 2026-05-18
type: 速查表
related:
  - "[[项目-签到管家]]"
  - "[[2026-05-18-MVP5上线+两个P0_hotfix]]"
---

# 规范增加字段 · manifest.yaml 速查

> 写新签到脚本时,在 `scripts/<slug>/manifest.yaml` 的 `fields:` 段声明字段。
> UI 自动按字段类型渲染对应控件,**完全零前端/后端代码改动**。
> 改完 manifest → 浏览器点"重新扫描"(或 MVP-5 上线后在线编辑器 `✏️ 保存`)→ 实例表单立刻多出新字段。

---

## TL;DR

11 种字段类型覆盖 95%+ 真实需求:

| type          | 控件                        | 加密?           | 常用于                               |
| ------------- | ------------------------- | ------------- | --------------------------------- |
| `string`      | 单行文本                      | 否             | 用户名 / API endpoint                |
| `secret`      | 密码框 + ••• 显示              | **是(Fernet)** | **密码 / cookie / token / API key** |
| `integer`     | 数字框(可 min/max)            | 否             | 数量 / 阈值 / 超时                      |
| `boolean`     | 开关                        | 否             | 启用/禁用某功能                          |
| `select`      | 下拉单选                      | 否             | 模式选择                              |
| `multiselect` | 下拉多选                      | 否             | 多账号 / 多任务                         |
| `multiline`   | 多行文本                      | 否             | 长 cookie / 备注                     |
| `cron`        | cron 输入 + 人话翻译 + 未来 5 次预览 | 否             | 自定义调度                             |
| `url`         | URL 输入 + 格式校验             | 否             | webhook / API base                |
| `json`        | JSON 编辑器 + 语法校验           | 否             | 复杂结构化配置                           |

⚠️ **任何凭证(密码/cookie/token/API key)必须用 `secret`**,它会自动 Fernet 加密落库,前端再也看不到明文。

---

## 完整范例(可直接 copy + 改)

下面这个范例覆盖**全部 11 种字段类型**,你写新脚本时按需删减即可。

```yaml
slug: example-script              # 全局唯一,英文小写横线
name: 某网站每日签到
description: |
  这里写脚本干什么。支持 markdown。

  ## 准备工作
  1. 浏览器登录
  2. F12 拿 cookie ...
version: 1.0.0
author: yunkelai
homepage: https://example.com/

default_cron: "0 9 * * *"         # 默认 cron(用户建实例可改)
default_timeout_sec: 300          # 默认超时(必须 ≥ random_delay + 60)
icon: icon.svg

fields:
  # ========== 1. string(用户名等明文短文本)==========
  - key: username
    label: 用户名
    type: string
    required: true
    placeholder: "your@email.com"
    description: "登录用的用户名或邮箱"

  # ========== 2. secret(密码 / cookie / token / API key)==========
  # ⚠️ 任何凭证都用这个!Fernet 加密落库,前端再也看不到明文
  - key: password
    label: 密码
    type: secret
    required: true
    description: "登录密码,加密存储"

  - key: cookie
    label: Cookie
    type: secret
    required: false
    description: "可选,有 cookie 优先用免登录;无则走密码登录"
    placeholder: "name1=val1; name2=val2"

  - key: api_token
    label: API Token
    type: secret
    required: false

  # ========== 3. integer(数字,可 min/max)==========
  - key: max_files
    label: 每日下载文件上限
    type: integer
    default: 5
    min: 0
    max: 100

  - key: random_delay_sec
    label: 随机延迟(秒)
    type: integer
    default: 1800
    min: 0
    max: 7200
    description: |
      0~N 秒随机 sleep 后签到,避开固定时刻被风控。
      ⚠️ **实例 timeout 必须 ≥ 本字段 + 60 秒**,否则被强杀。

  # ========== 4. boolean(开关)==========
  - key: skip_if_signed
    label: 已签到时跳过
    type: boolean
    default: true
    description: "签到前先查状态,已签到则直接 success 不重复请求"

  - key: enable_check_in_bonus
    label: 是否领取每日奖励
    type: boolean
    default: true

  # ========== 5. select(下拉单选,从固定列表选 1)==========
  - key: signin_method
    label: 签到方式
    type: select
    default: "auto"
    options:
      - { value: "auto", label: "自动(默认)" }
      - { value: "api",  label: "强制走 API" }
      - { value: "web",  label: "强制走 Web 模拟" }

  # ========== 6. multiselect(下拉多选)==========
  - key: skip_tasks
    label: 跳过的任务(可多选)
    type: multiselect
    default: []
    options:
      - { value: "share",   label: "分享" }
      - { value: "comment", label: "评论" }
      - { value: "like",    label: "点赞" }
      - { value: "vote",    label: "投票" }

  # ========== 7. multiline(多行文本)==========
  - key: extra_note
    label: 备注
    type: multiline
    required: false
    placeholder: "可写多行,自己看的备注"

  - key: target_bvids
    label: 投币目标 BV 号
    type: multiline
    required: false
    description: "一行一个 BV 号,留空自动找"

  # ========== 8. cron(自定义调度,覆盖 default_cron)==========
  - key: custom_cron
    label: 自定义 cron 表达式
    type: cron
    required: false
    description: "留空 = 用脚本默认 cron"
    placeholder: "0 9 * * *"

  # ========== 9. url(URL 输入 + 格式校验)==========
  - key: webhook_url
    label: 签到完成后回调 URL
    type: url
    required: false
    placeholder: "https://hook.example.com/notify"

  - key: custom_api_base
    label: 自建 API 端点
    type: url
    required: false
    default: "https://api.example.com"

  # ========== 10. json(JSON 编辑器 + 语法校验)==========
  - key: advanced_rules
    label: 高级规则(JSON)
    type: json
    default: {}
    description: |
      复杂结构化配置,前端有语法高亮 + 校验。
      例:{"max_retries": 3, "tags": ["x", "y"]}

runtime:
  python_version: ">=3.10"
  isolated: true
  env_passthrough:               # 白名单环境变量
    - HTTP_PROXY
    - HTTPS_PROXY
    - NO_PROXY
  dependencies_file: requirements.txt
```

---

## 字段通用属性

每个字段都可以加这些属性(任何 type 都接受):

| 属性 | 说明 | 例子 |
|---|---|---|
| `key` | **必需**,代码里 `config["key"]` 用 | `cookie` |
| `label` | **必需**,UI 显示的中文标签 | `Cookie` |
| `type` | **必需**,11 种之一 | `secret` |
| `required` | 是否必填(默认 `false`) | `true` |
| `default` | 默认值(类型对齐 type) | `1800` |
| `description` | 字段下方的灰色帮助文字 | `"30 分钟随机延迟..."` |
| `placeholder` | 输入框灰色占位符 | `"your@email.com"` |

部分 type 还有专属属性:
- `integer`:`min` / `max`(数字范围 + 滑块)
- `select` / `multiselect`:`options: [{value, label}, ...]`(选项列表)

---

## 常见模式 — "我想做 X 用什么?"

| 我想要 | 用什么字段 | 例 |
|---|---|---|
| **账号 + 密码登录** | `string` + `secret` | `username: string` / `password: secret` |
| **Cookie 免登录** | `secret` | `cookie: secret`(全部 cookie 字符串粘) |
| **API key** | `secret` | `api_token: secret` |
| **任选一种登录方式** | `select` | `auth_mode: select [cookie/password/api]` |
| **数量上限(每天最多 N 次)** | `integer` 带 `min: 1, max: 100` | `max_signin: integer` |
| **开/关某项功能** | `boolean` | `enable_share: boolean default: true` |
| **多账号/多目标** | `multiselect` 或多行 | `target_users: multiselect` 或 `target_users: multiline` |
| **复杂结构(对象数组)** | `json` | `rules: json default: []` |
| **每天签到时刻不同** | `cron` | `custom_cron: cron` |
| **回调通知** | `url` | `webhook: url` |
| **风控避开:随机延迟** | `integer` + sanity check | `random_delay_sec: integer default: 1800` |
| **调试时跳过部分逻辑** | `boolean` | `debug_dry_run: boolean default: false` |

---

## 加字段的 3 种方式(对应不同熟练度)

### 方式 ① SSH + 直接改文件(老派)

```bash
ssh root@154.9.238.144
cd /opt/signin-panel/scripts/<slug>
vim manifest.yaml      # 加字段
# 自动 host volume,容器立刻看到,无需 restart
# 浏览器 /scripts 点"重新扫描" → 实例表单刷新
```

### 方式 ② 本机 rsync(中间)

```bash
# 本机改 E:\签到脚本多合一\scripts\<slug>\manifest.yaml
rsync -avz scripts/<slug>/ root@154.9.238.144:/opt/signin-panel/scripts/<slug>/
# 浏览器扫描
```

### 方式 ③ 浏览器在线编辑(MVP-5,最爽,推荐)

1. https://jb.aijiaxia.cc/scripts/`<slug>` → 概览 Tab → 文件列表
2. 点 `manifest.yaml` 旁的 **`✏️ 编辑`**
3. CodeMirror 编辑器打开 → `fields:` 段加新字段 → `Ctrl+S` 保存
4. 自动 dry-run 校验 → 通过 → 自动备份旧版到 `.backups/` + 落盘 + 重新扫描
5. **该脚本所有实例表单立刻多出新字段**(已有实例字段值=该字段 default,可编辑实例填新值)

**全程不离开浏览器,30 秒搞定**。失败的话 dry-run 红色提示具体哪行错。

---

## 校验规则(后端帮你拦的)

后端 manifest_parser 会校验:
- `slug` 全局唯一,正则 `^[a-z][a-z0-9_-]{1,40}$`
- `fields[].key` 在脚本内唯一,正则 `^[a-zA-Z_][a-zA-Z0-9_]*$`
- `type` 必须是 11 种之一
- `default` 类型必须对齐 `type`(给 `integer` 写 `"abc"` 会 422 拒绝)
- `options` 在 `select` / `multiselect` 时必填
- `min` / `max` 在 `integer` 时可选

写错了浏览器立刻看到 422 红字"manifest.yaml 校验失败:fields[3].type 必须是 string/secret/.../json 之一"。

---

## 已有的真实脚本范例(参考它们改)

| Slug | 字段构成 | 适合参照场景 |
|---|---|---|
| `scripts/coklw/manifest.yaml` | cookie / random_delay_sec / user_agent / skip_if_signed | **WordPress 类站点** / 简单 cookie 签到 |
| `scripts/ptfans/manifest.yaml` | 同 coklw(NexusPHP 是 WP fork) | **PT 站 / NexusPHP** |

---

## 如果 11 种类型不够用(罕见,但留路)

未来真遇到 11 种覆盖不了的场景,**告诉 PM(Claude / 我)** 加个新类型即可:

| 假设需求 | 加什么 type | 估时 |
|---|---|---|
| 上传配置文件(.json/.yaml) | `file` | ~30 分钟 |
| 日期/时间选择 | `datetime` / `date` / `time` | ~20 分钟 |
| 颜色选择器 | `color`(react-colorful 已经装了) | ~10 分钟 |
| 标签输入(自由文本数组) | `tags` | ~20 分钟 |

但**不要预先加**,等真遇到再加 — YAGNI(You Aren't Gonna Need It)原则。

---

## 写新脚本完整 checklist

抓包 → manifest + main.py + requirements + icon + README,5 个文件:

- [ ] HAR 抓包(浏览器 Network → 全选 → Save all as HAR)
- [ ] 派 opus agent 分析 HAR(给 HAR 路径 + 网站 URL + 让它参照 coklw/ptfans)
- [ ] agent 写 5 文件,主要是 manifest fields 和 main.py 的 `run(config, context)`
- [ ] dry-run 测试(空 cookie 应该优雅 fail + exit 1)
- [ ] 浏览器**上传 zip**(MVP-5 主流程)→ 自动扫描入库
- [ ] 建实例填字段 → 立即运行 → 看绿色 success
- [ ] 设 cron 让它 7×24 自动跑

详细规范见 [项目说明.md § 3](file:///E:/%E7%AD%BE%E5%88%B0%E8%84%9A%E6%9C%AC%E5%A4%9A%E5%90%88%E4%B8%80/%E9%A1%B9%E7%9B%AE%E8%AF%B4%E6%98%8E.md)。

---

## 链接

- [[项目-签到管家]] — 项目主记录
- [[2026-05-18-MVP5上线+两个P0_hotfix]] — MVP-5 上线总结(在线编辑器就在这次上的)
- [项目说明.md § 3](file:///E:/%E7%AD%BE%E5%88%B0%E8%84%9A%E6%9C%AC%E5%A4%9A%E5%90%88%E4%B8%80/%E9%A1%B9%E7%9B%AE%E8%AF%B4%E6%98%8E.md) — 完整脚本开发规范
- [scripts/coklw/manifest.yaml](file:///E:/%E7%AD%BE%E5%88%B0%E8%84%9A%E6%9C%AC%E5%A4%9A%E5%90%88%E4%B8%80/scripts/coklw/manifest.yaml) — 真实范例 1
- [scripts/ptfans/manifest.yaml](file:///E:/%E7%AD%BE%E5%88%B0%E8%84%9A%E6%9C%AC%E5%A4%9A%E5%90%88%E4%B8%80/scripts/ptfans/manifest.yaml) — 真实范例 2

---

📝 写于 2026-05-18
💡 用法:写新脚本前打开看一眼,改 manifest 时复制对应字段块改改就好
