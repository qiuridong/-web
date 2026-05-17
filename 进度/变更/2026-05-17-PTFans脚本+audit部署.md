---
name: 2026-05-17 · PTFans 第二个真签到脚本上线 + audit High 7 项一并部署生产
description: 完成"多合一"语义第一里程碑(脚本 N=2 真站点),audit High 修复同时上线
type: change
status: ✅ 已部署生产,smoke test 全绿
---

# 2026-05-17 晚 · PTFans 上线 + audit High 部署

## 30 秒摘要

1. **PTFans 第二个真签到脚本完成** — opus agent 分析 `D:\PTFans.har`(3.1MB / 65 entries)→ 写 5 文件(manifest 3KB / main.py 21KB / requirements 17B / icon 406B / README 8.6KB)→ dry-run 3/3 过。NexusPHP 纯 GET `/attendance.php` 触发签到,无 CSRF / 无 turnstile(已登录态),唯一 cookie `c_secure_pass` 1+ 年有效。
2. **audit High 7 项加固一并部署**(打包一次 docker rebuild,节省一次重启窗口)
3. **生产 smoke test 全绿**:`/health` 200 / `/openapi.json` **404**(#9 生效)/ `/api/v1/runs?order=asc` 401(#13 参数被 pattern 接受,被 auth 拦正常)
4. **修了一个我自己写错的文档** — `项目说明.md` § 3.3 原本写脚本协议是"裸 stdin/stdout",实际 sandbox 用 `run(config, context) -> RunResult` 函数模型(coklw 同款)。已修正为正确范例
5. **多合一语义正式成立**:N=2(coklw 国内 WordPress / ptfans PT 站 NexusPHP),验证 manifest + sandbox 协议对不同框架的通用性

## PTFans 脚本细节

| 项 | 值 |
|---|---|
| slug | `ptfans` |
| 站点 | https://ptfans.cc/(NexusPHP,PT 站,Cloudflare 后) |
| 签到接口 | **GET** `/attendance.php`(纯幂等 GET,无 POST 无 CSRF) |
| 状态检查 | **GET** `/index.php` 顶部用户栏文本 `[签到已得 X]` 判定 |
| 必需 cookie | `c_secure_pass`(NexusPHP 唯一登录态,base64 含 user_id+expires+签名,~144 字节) |
| Cookie 有效期 | 1+ 年(HAR 实测) |
| 反爬 | Cloudflare(cf-ray / cf-cache-status 确认),已登录态访问未触发 challenge |
| 默认 cron | `0 9 * * *` |
| 默认 timeout | 2000 秒(覆盖 1800s 随机延迟 + 200s 余量) |
| 默认随机延迟 | 0–1800 秒(签到落在 9:00–9:30 之间) |
| 字段 | cookie(secret 必需) / random_delay_sec(integer 默认 1800) / user_agent(string 可选) / skip_if_signed(boolean 默认 true) |

### 异常体系(agent 设计扎实)

- `CookieMissingError` — cookie 字段空 / 缺 c_secure_pass
- `CloudflareBlockError` — 4xx/503 + 识别 CF challenge HTML
- `NotLoggedInError` — 响应不含登录态标识(cookie 已过期)
- `PTFansError` — 站点其它错误(HTTP 非 200 / 解析失败)
- `httpx.HTTPError` — 网络层(超时 / DNS / TLS)

每条都有友好中文消息 + 不抛 Python traceback 给用户看。

### 备用方案(本期未做)

agent 报告里说 PTFans 登录大概率走 `POST /takelogin.php` 极可能触发 Cloudflare turnstile。本期 cookie 优先(1+ 年有效),password 登录留给以后(需要 turnstile 绕过研究)。`README.md` 已写明这一点。

## audit High 修复(本次合并部署)

详见昨天的变更档案 [`2026-05-17-audit-High-7项加固.md`](2026-05-17-audit-High-7项加固.md)。已部署 7 项 High(#7/#9/#10/#11/#12/#13/#15)+ ADR 锁定 #14。

## 部署过程

```bash
# 1. 打包(本机 E:\签到脚本多合一)
tar czf /tmp/mvp5-ptfans.tar.gz backend/app scripts/ptfans
# → 342K 压缩包(干净,仅必要文件)

# 2. scp 到生产
scp -i J:/密钥/美国质量8-8/vcs-deploy-rsa /tmp/mvp5-ptfans.tar.gz root@154.9.238.144:/tmp/

# 3. SSH 解压 + docker rebuild
ssh ... "cd /opt/signin-panel && tar xzf /tmp/mvp5-ptfans.tar.gz && \
  docker compose build backend && docker compose up -d backend"
# → backend container Recreated + Started,约 30 秒

# 4. smoke test
curl https://jb.aijiaxia.cc/health                              # 200 ✅
curl https://jb.aijiaxia.cc/openapi.json                        # 404 ✅(#9)
curl https://jb.aijiaxia.cc/api/v1/runs?order=asc               # 401 ✅(#13 通过参数校验,被 auth 拦)
```

期间生产 API 中断约 5 秒(docker compose recreate backend),用户数据 / 主密钥 / cookie 配置全部保留(只重建镜像,data volume 不动)。

## 验证(本机)

| Verify 脚本 | 断言数 | 结果 |
|---|---|---|
| 6 个 verify 全跑 | **178** | ✅ exit 0(MVP-5 加固未破坏既有功能) |

## 修了 / 文档纠错

### `项目说明.md` § 3.3 main.py 协议(我写错了 → 修正)

**原写**:脚本从 `sys.stdin.read()` 读 JSON 配置,自己 `print("__RUN_RESULT__"+...)`,自己 `sys.exit(...)`。**`status` 是 enum `success/failure/skipped`**。

**实际**(读 `backend/sandbox_runner.py` 后确认):
- 脚本定义顶级函数 `run(config, context) -> RunResult`
- `config` 是 dict(secret 已解密)
- `context` 是 `SimpleNamespace`,含 `script_dir` / `data_dir` / `logger` / `notify` / `timeout_sec` 等
- `RunResult` 是 dataclass 含 `success: bool` / `message: str` / `data: dict`(**没有 status 三态枚举**,已签到也是 success 在 message 里说)
- **不要自己打 marker、不要自己 `sys.exit`** —— sandbox_runner 包装

修正了 `项目说明.md` 第 3.3 节(完整 60 行新范例)+ 第 3.6 节铁律表(改"必须打 marker"为"不要自己打 marker、不要 sys.exit")。

## 用户拿真 cookie 上线 PTFans 实例的步骤

1. 浏览器登录 https://ptfans.cc/(勾"记住我"延长 cookie 有效期)
2. F12 → Application → Cookies → `https://ptfans.cc` → 找 `c_secure_pass` 复制 value
3. 拼成字符串 `c_secure_pass=<value>`
4. 浏览器打开 https://jb.aijiaxia.cc/scripts → 右上角"重新扫描"按钮 → 看到 PTFans 卡片
5. 点 PTFans 卡片进详情 → 实例 Tab → 创建实例 → 粘 cookie + 设 cron(可保持默认 `0 9 * * *`)→ 保存
6. 实例 Tab 找到刚建的 → 点"立即运行" → 看实时日志确认签到成功

## 文件清单(本次部署)

新建:
- `scripts/ptfans/manifest.yaml` 3002
- `scripts/ptfans/main.py` 21053
- `scripts/ptfans/requirements.txt` 17
- `scripts/ptfans/icon.svg` 406
- `scripts/ptfans/README.md` 8680

修改(audit High 加固,昨天已写完今天部署):
- `backend/app/config.py` / `backend/app/main.py`(#9)
- `backend/app/core/exceptions.py` / `backend/app/deps.py`(#12)
- `backend/app/services/script_service.py` / `backend/app/api/v1/scripts.py`(#7)
- `backend/app/services/instance_service.py`(#10)
- `backend/app/schemas/instance.py` / `backend/app/api/v1/instances.py`(#11)
- `backend/app/api/v1/runs.py` / `backend/app/services/run_service.py`(#13)
- `backend/app/notifications/dispatcher.py`(#14 ADR 锁定)
- `backend/app/api/v1/settings.py` / `backend/app/schemas/setting.py`(#15)

修改(文档):
- `项目说明.md` § 3.3(协议范例从裸 stdin 改 `run(config, context)`)+ § 3.6 铁律表

## 风险与后续

- ⚠️ PTFans 顶部用户栏正则基于 1 次抓包样本,主题改动可能失效。已有防御性兜底(`_signed_already_in_text` + `_check_signed_status` 双重)+ README 故障排查表
- ⚠️ NexusPHP 二次访问 `/attendance.php` 的响应文案不确定(HAR 没二次样本)。`skip_if_signed=true` 已尽量避免走到二次
- ✅ Cloudflare 已登录态不触发 challenge,但用户换 IP / 频繁访问可能触发 → `_detect_cloudflare_challenge` 兜底友好报错
- 未实现 password 登录(turnstile 绕过工作量大,cookie 1+ 年有效足够)

## 后续(下一里程碑)

按用户需求:
1. **改用户名**(用户尚未告诉新名字,在等)
2. **Web 上传脚本 MVP-5**(react-dropzone + 5 后端 API,设计稿 [`设计/Web脚本编辑器.md`](../设计/Web脚本编辑器.md))
3. **再添脚本**(B 站 / V2EX 等,验证标准通用性继续 N=3,4...)
4. **restic 备份 cron**(P2,生产 `data/` 增量备份到远端)
5. **observability**(Prometheus + Grafana,MVP-6 候选)
