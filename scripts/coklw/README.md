# COKLW 每日签到

> 站点:https://coklw.net/(WordPress + Cloudflare 防护的 ACG 资源站)
> 实现:用户提供登录 cookie,脚本走 `wp-admin/admin-ajax.php` 走完整签到流程。
> 不实现登录路径(避开 Cloudflare turnstile challenge)。

## 字段

| key | type | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cookie` | secret | 是 | — | 登录后的 cookie 字符串。**必须包含** `wordpress_logged_in_*` 项 |
| `random_delay_sec` | integer | 否 | 3600 | 启动后随机 sleep 0~N 秒,默认 1 小时 |
| `user_agent` | string | 否 | Edge 148 UA | 自定义 UA,建议保持与抓包浏览器一致 |
| `skip_if_signed` | boolean | 否 | true | 已签到时直接返回 success,不再请求签到接口 |

## Cookie 怎么拿

1. 浏览器(Edge / Chrome 都行)登录 https://coklw.net/
2. F12 打开开发者工具 → 顶部 **Application**(应用)标签 → 左侧 **Storage** → **Cookies** → 选中 `https://coklw.net`
3. 把 `Name` / `Value` 列的 cookie 拷成 `name1=value1; name2=value2` 的形式;**至少**要有一项叫 `wordpress_logged_in_<32位hex>`,最好把 `wordpress_sec_<32位hex>` 也带上
4. 粘贴到面板的 Cookie 字段(secret 类型,会被 Fernet 加密落库)
5. WordPress 默认 cookie 有效期 48 小时,登录时勾"记住我"则 14 天;过期后需重新提供

> 快捷做法(Chrome / Edge 控制台):打开 coklw.net 后 F12 → Console 输入 `document.cookie` 回车 → 拷出来的就是 `name1=val1; name2=val2` 字符串(注意 HttpOnly 的 cookie 在 Console 看不到,需用 Application 面板手动拼)。

## 签到时刻策略

- `default_cron: "0 9 * * *"` — 调度器每天北京时间 9:00 触发
- `random_delay_sec: 3600` — 脚本进程启动后随机 sleep 0–3600 秒
- 综合效果:实际签到时刻均匀分布在 9:00–10:00 之间,既避开整点又不重复扫描
- 调试时把 `random_delay_sec` 设 0 即可立即签到

## 本地测试

脚本可独立运行,不依赖主程序的 sandbox runner。

```powershell
# 1. 装依赖
pip install httpx

# 2. 进入目录(注意中文路径需引号)
cd "E:\签到脚本多合一\scripts\coklw"

# 3. 设置 cookie 与 delay,跑一次
$env:COKLW_COOKIE = "wordpress_logged_in_xxx=yyy; wordpress_sec_xxx=zzz"
$env:COKLW_DELAY  = "0"      # 跳过随机延迟
$env:COKLW_DEBUG  = "1"      # 打开 DEBUG 日志,看 URL
python main.py
```

输出示例:

```json
{
  "success": true,
  "message": "成功获取了签到奖励,你是第 3781 个签到勇士!",
  "data": {
    "already_signed": false,
    "user": "炙烈の影",
    "point": 117,
    "response": {
      "code": 0,
      "data": { "imgUrl": "" },
      "msg": "成功获取了签到奖励,你是第 3781 个签到勇士!"
    }
  }
}
```

退出码:成功 = 0,失败 / 异常 = 1。

或者一次给完整 JSON config:

```powershell
$env:COKLW_CONFIG = '{"cookie":"wordpress_logged_in_xxx=yyy","random_delay_sec":0,"skip_if_signed":true}'
python main.py
```

## 接口逆向(给后人看 / 检修参考)

来自 `D:\coklw.har` 抓包(Edge 148 / 2026-05-XX):

| 用途 | 方法 + 路径 | 关键参数 |
|---|---|---|
| 状态聚合 | `GET /wp-admin/admin-ajax.php` | `action=a1695e2e97b11317858156779ec6ab41` + 子查询 `<inner_action_hash>[type]=<sub>` |
| 签到 | `GET /wp-admin/admin-ajax.php` | `?_nonce=<n>&action=07e2fafdb61c964ff31938b1ac72ace4&type=goSign` |
| 登录(本脚本不用) | `POST /wp-admin/admin-ajax.php?_nonce=<n>&action=dd3e2aa1548380622059abb314f9077c&type=login` | multipart `email/pwd/type=login` |

**WordPress action 是 hash 后的**,推测主题(KratosPro/JustNews 之类)做了一次 `md5(real_action + secret_salt)`。从 HAR 多次访问发现 action hash 在不同会话/不同用户间稳定,说明 salt 是站点常量而非用户态 — 可以直接硬编码。

**`_nonce` 是与会话绑定的**:

- 已登录态调状态接口拿到的 nonce(如 `0f936b5151`)与未登录态(`0ee8f3a4e5`)不一样
- 同一登录会话内 nonce 在合理时间内可复用(WP 默认 12h)
- 所以脚本流程必须先调状态接口拿 nonce,再用它调签到 — **不能** 跳过状态步骤

**判定签到结果**:

- 成功:`{"code":0,"data":{"imgUrl":"..."},"msg":"成功获取了签到奖励,你是第 N 个签到勇士!"}`
- 已签到:状态接口的 `customPointSignDaily.signed === true`(本脚本优先看这个,不依赖签到接口的"已签到"提示)
- 失败/未登录:`code != 0` 或 `user` 字段缺失

**最小 cookie 集**:

- 必需:`wordpress_logged_in_<COOKIEHASH>` —— WP 登录态判定的核心 cookie
- 推荐:`wordpress_sec_<COOKIEHASH>` —— admin-ajax 路径下 `secure; HttpOnly`,部分接口会校验
- 可省略:`crisp-client_*`(Crisp 客服 widget,跟签到无关)

`COOKIEHASH` 是 WP 站点 install 时算出的常量(`md5(siteurl)`),coklw.net 当前是 `018e703ef8666f6cb246fdc5a709d6b4`,但脚本不写死 — 用前缀匹配 `wordpress_logged_in_*` 即可。

## 已知局限

1. **Cookie 会过期** —— WP 默认 48h(无"记住我")或 14 天(有"记住我")。签到失败若 message 含"cookie 可能已过期"即提示用户重新提供。
2. **Cloudflare turnstile 触发概率低,但可能** —— 若站点突然加严风控,`_validate_cookie` 之后可能在状态接口直接收到 challenge HTML(JSON 解析会失败),错误信息会透传到 RunResult.message。
3. **action hash 可能因主题升级而变** —— 若站点升级了 WordPress 主题,两个 action hash 可能改变。届时需重新抓包并更新 `STATUS_ACTION` / `SIGN_ACTION` 常量。
4. **没有自动登录** —— 脚本设计上不实现 email+pwd 登录路径(会面对 turnstile,复杂且不稳),只支持 cookie 复用。

## 故障排查

| RunResult.message 模式 | 原因 | 处理 |
|---|---|---|
| `Cookie 字段为空 ...` | 没填 cookie | 在面板 Cookie 字段填入 |
| `Cookie 字符串中未找到 wordpress_logged_in_*` | cookie 不全或复制错了站点 | 重新从 coklw.net 复制完整 cookie |
| `状态接口未返回用户信息,cookie 可能已过期` | cookie 过期 | 重新登录复制 |
| `状态接口 HTTP 403 / 503 / 429` | Cloudflare 拦截 | 检查 IP / 换 UA / 短期降低频率 |
| `状态接口返回非 JSON: ...` | 收到 challenge HTML | 同上 |
| `签到失败: code=N, msg=...` | WordPress 端拒绝(频率 / 风控 / 已签等) | 看 msg 判断;若 msg 含"已签"会自动归类成功 |

## 相关文件

- `manifest.yaml` — 字段定义、调度默认值、runtime 声明
- `main.py` — 唯一入口,暴露 `run(config, context) -> RunResult`
- `requirements.txt` — `httpx>=0.27`
- `icon.svg` — 32×32 单色 lucide 风格图标
