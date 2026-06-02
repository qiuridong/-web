# PTFans 每日签到

> 站点:https://ptfans.cc/(NexusPHP 框架的 PT 私有种子站,Cloudflare 防护)
> 实现:用户提供登录 cookie(`c_secure_pass`),脚本走 NexusPHP 标准签到 endpoint。
> **不实现** email/密码登录(避开 Cloudflare turnstile / captcha 挑战)。

## 字段

| key | type | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cookie` | secret | 是 | — | 登录后的 cookie 字符串。**必须包含** `c_secure_pass=...` 项 |
| `random_delay_sec` | integer | 否 | 1800 | 启动后随机 sleep 0~N 秒,默认 30 分钟,均匀分布签到时刻 |
| `user_agent` | string | 否 | Edge 148 UA | 自定义 UA,建议保持与抓包浏览器一致 |
| `skip_if_signed` | boolean | 否 | true | 已签到时直接返回 success,不再请求 `/attendance.php` |

## Cookie 怎么拿

1. 浏览器(Edge / Chrome 都行)登录 https://ptfans.cc/(勾"记住我"延长有效期)
2. F12 打开开发者工具 → 顶部 **Application**(应用)标签 → 左侧 **Storage** → **Cookies** → 选中 `https://ptfans.cc`
3. 找到 **`c_secure_pass`** 这一行(必需,~144 字符的 base64),复制其 Value
4. 拼成 `c_secure_pass=eyJ1c2VyX...` 字符串粘贴到面板的 Cookie 字段(secret 类型,会被 Fernet 加密落库)
5. 若顺手把其它 cookie 也带上也可,格式 `name1=val1; name2=val2`

> 快捷做法:浏览器打开 ptfans.cc → F12 → Console 输入
> `document.cookie` 回车 → 拷出来的就是 `name1=val1; name2=val2` 字符串(注意 `c_secure_pass` 在 ptfans.cc 是 `secure; HttpOnly`,Console 看不到,必须用 Application 面板手动拼)。

### `c_secure_pass` 有效期

PTFans 的 `c_secure_pass` 是 NexusPHP 签发的长期 cookie,有效期取决于站点配置:

- HAR 里实测一条 cookie 的 `expires` 字段是 `2027-04-12`(签发后约 540 天),典型 1-2 年
- 远长于普通 PHP session,通常不需要频繁更新
- 改密 / 主动退出 / 站点 reset cookie 会失效

## 签到时刻策略

- `default_cron: "0 9 * * *"` — 调度器每天北京时间 9:00 触发
- `random_delay_sec: 1800` — 脚本进程启动后随机 sleep 0–1800 秒
- 综合效果:实际签到时刻均匀分布在 9:00–9:30 之间,避开整点峰值
- 调试时把 `random_delay_sec` 设 0 即可立即签到

## 本地测试

脚本可独立运行,不依赖主程序的 sandbox runner。

```powershell
# 1. 装依赖
pip install httpx

# 2. 进入目录(注意中文路径需引号)
cd "E:\签到脚本多合一\scripts\ptfans"

# 3. 设置 cookie 与 delay,跑一次
$env:PTFANS_COOKIE = "c_secure_pass=eyJ1c2VyX2lkIjoxMjM0NSwiZXhwaXJlcyI..."
$env:PTFANS_DELAY  = "0"      # 跳过随机延迟
$env:PTFANS_DEBUG  = "1"      # 打开 DEBUG 日志,看 URL
python main.py
```

输出示例(签到成功):

```json
{
  "success": true,
  "message": "签到成功 / 获得 30.0 魔力值 / 连续 5 天 / 第 20 次 / 今日排名 2344",
  "data": {
    "already_signed": false,
    "user": "aijiaxia0409",
    "user_id": 21550,
    "bonus": 749.1,
    "bonus_gained": 30.0,
    "total_times": 20,
    "continuous_days": 5,
    "today_rank": 2344
  }
}
```

输出示例(已签到跳过):

```json
{
  "success": true,
  "message": "今日已签到(首页确认,今日得 30.0 魔力值)",
  "data": {
    "already_signed": true,
    "user": "aijiaxia0409",
    "user_id": 21550,
    "bonus": 749.1,
    "today_gain": 30.0
  }
}
```

退出码:成功 = 0,失败 / 异常 = 1。

或者一次给完整 JSON config:

```powershell
$env:PTFANS_CONFIG = '{"cookie":"c_secure_pass=eyJ1...","random_delay_sec":0,"skip_if_signed":true}'
python main.py
```

## 接口逆向(给后人看 / 检修参考)

来自 `D:\PTFans.har` 抓包(Edge 148 / 2026-05-17):

| 用途 | 方法 + 路径 | 关键参数 |
|---|---|---|
| 首页(读用户名 + 已签状态) | `GET /index.php` | cookie: `c_secure_pass=<base64>` |
| 签到(此请求即完成今日签到) | `GET /attendance.php` | cookie: `c_secure_pass=<base64>` |
| 补签(本脚本不实现) | `POST /ajax.php` | `params.date=YYYY-MM-DD` + `action=attendanceRetroactive`,需补签卡 |
| 登录(本脚本不实现) | `POST /takelogin.php` | NexusPHP 标准登录表单,极可能触发 Cloudflare turnstile |

### NexusPHP 签到机制

NexusPHP 的签到是**纯粹幂等的 GET 请求** —— 一访问 `attendance.php` 就完成签到,不需要 POST,不需要 CSRF token,不需要 `_nonce`:

- 首次访问当日 `attendance.php` → 触发签到 + 返回 `<h2>签到成功</h2>` + 详情段
- 同日二次访问 → 不再加分,返回的页面(可能)只有日历视图,或者也带"今天已签"提示
- 因此本脚本**先访问 `/index.php`** 读顶部用户区,通过 `[签到已得 X]` vs `[签到得魔力]` 字样判断当日状态;只有未签时才请求 `/attendance.php`

### 顶部用户栏状态识别

NexusPHP 顶部用户栏的签到入口链接文字,是判定今日是否已签的最可靠 marker:

| HTML 模式 | 含义 |
|---|---|
| `<a href="attendance.php" class="">[签到已得 X, 补签卡: Y]</a>` | 今日已签,得 X 魔力,有 Y 补签卡 |
| `<a href="attendance.php" class="faqlink">[签到得魔力]</a>` | 今日未签,可签 |

(从 HAR 同一会话的两个不同页面 `torrents.php` vs `attendance.php` 对比得到上述 2 种状态;若站点改版可能需更新正则)

### 签到响应解析模式

`attendance.php` 首次访问的响应 HTML 中,关键字段:

```html
<h2 align="left">签到成功</h2>
<table ...>
  <p>这是您的第 <b>20</b> 次签到,已连续签到 <b>5</b> 天,
     本次签到获得 <b>30</b> 个魔力值。...
     <span style="float:right">今日签到排名:<b>2344</b> / <b>2344</b></span></p>
</table>
```

正则提取:`本次签到获得 <b>(\d+)</b>` / `这是您的第 <b>(\d+)</b>` / `已连续签到 <b>(\d+)</b>` / `今日签到排名:<b>(\d+)</b>`。

### 最小 cookie 集

- 必需:`c_secure_pass` —— NexusPHP 唯一登录态 cookie(含 `user_id` + `expires` + 签名)
- 可省略:CSS / JS 加载相关的辅助 cookie(无)

`c_secure_pass` 是 base64 编码的 JSON + HMAC 签名,典型形式:
`eyJ1c2VyX2lkIjoxMjM0NSwiZXhwaXJlcyI6MTgwNzIyOTQ0NX0.<64字符 hex 签名>`(URL-encoded)。

## 备用方案(未来扩展)

若 cookie 过期且用户希望脚本自动续期,需实现密码登录:

- **登录路径**:`POST /takelogin.php`(form-data 含 `username` / `password` / 可能含 `securelogin`)
- **风险**:NexusPHP 站点+Cloudflare 极可能触发 turnstile / hCaptcha challenge
- **绕过难度**:中-高,需要 headless Chrome + cloudscraper / turnstile solver 服务
- **本期决定**:**不实现**,优先保证 cookie 模式稳定。cookie 过期由用户重新登录浏览器后粘贴 ~5 秒解决。

如果未来希望支持,建议:
1. 单独走另一个 `auto_login=true` 字段触发
2. 后端额外提供 turnstile API key 配置
3. 引入 [DrissionPage](https://github.com/g1879/DrissionPage) 之类 webdriver

## 已知局限

1. **Cookie 会过期** —— 普通 PT 站 `c_secure_pass` 有效期 1-2 年,改密 / 主动 logout / 站点重置会失效。签到失败若 message 含"cookie 已过期"即提示用户重新提供。
2. **Cloudflare turnstile 概率触发** —— 若你 IP 进 CF 黑名单或同 IP 大量访问 ptfans.cc,可能首次访问就收到 challenge HTML,脚本会返回 `Cloudflare 拦截` 错误。
3. **页面正则可能因主题升级失效** —— PTFans 用了 `BambooGreen` 主题,若升级主题或换主题,顶部 HTML 结构可能变化,需重抓 HAR 并更新 `RE_SIGNED_TODAY` / `RE_NOT_SIGNED` / `RE_GAIN_BONUS` 等正则。
4. **没有自动登录** —— 见"备用方案"段。

## 故障排查

| RunResult.message 模式 | 原因 | 处理 |
|---|---|---|
| `Cookie 字段为空 ...` | 没填 cookie | 在面板 Cookie 字段填入 |
| `Cookie 字符串中未找到 c_secure_pass=...` | cookie 不全或复制错了站点 | 重新从 ptfans.cc Application 面板复制 `c_secure_pass` |
| `首页未识别到用户名 ... cookie 已过期` | cookie 失效 | 重新登录浏览器复制新 cookie |
| `Cloudflare 拦截(HTTP 403/503/429)...` | CF 风控 | 检查 IP / 换 UA / 短期降低频率 / 关 VPN |
| `首页 HTTP <非200> ...` | 网络异常 / DNS / 服务器宕 | 看 message 详细,稍后重试 |
| `签到接口响应未识别(无成功/失败 H2)...` | 页面改版 | 看 data.html_excerpt 字段,联系开发者更新正则 |

## 相关文件

- `manifest.yaml` — 字段定义、调度默认值、runtime 声明
- `main.py` — 唯一入口,暴露 `run(config, context) -> RunResult`
- `requirements.txt` — `httpx>=0.27`
- `icon.svg` — 32×32 单色 lucide 风格图标(下载圆圈)
