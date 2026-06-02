/**
 * 脚本模板生成器 — 与「签到管家」脚本格式**完全一致**（货架产出的脚本就是给管家跑的）。
 *
 * UploadDialog 顶部「下载模板」按钮触发，前端用 jszip 动态拼装 zip（纯前端，无需后端）。
 * 模板带详细中文注释，看了就懂平台协议。上传的 zip 必须符合此格式才能被管家接受。
 */
import JSZip from 'jszip';

// ============================================================
// manifest.yaml 模板
// ============================================================
export const MANIFEST_TEMPLATE = `# ====================================================================
# 签到脚本 · manifest（货架与签到管家通用格式）
# ====================================================================
# 必填:slug / name / version
# slug 必须等于本目录名（小写字母开头，a-z 0-9 -，长度 1-41）
# version 必须是 SemVer（如 1.0.0 / 1.0.0-rc1）
#
# 字段类型（11 种）:string / secret / integer / boolean / select /
#                    multiselect / multiline / cron / url / json
# ====================================================================

slug: my-script              # ⚠️ 改成你的 slug，必须与目录名一致
name: 我的签到脚本           # 显示名（中文 OK）
version: 1.0.0
description: |
  ⚠️ 提交前 checklist:
  - main.py 顶部的 "dry-run 短路" 段不能删（否则上传必失败 HTTP 422）
  - slug 改成与目录名一致
  - 至少改一次 version

  在这里写一段 markdown 说明，讲清楚:
  - 这是哪个站点的签到?
  - 用户拿凭证（cookie / 账密）的方法
  - 已知失败模式与处理
author: your-name
homepage: https://example.com

# ============ 调度 ============
default_cron: "0 1 * * *"    # UTC 1 点 = 北京 9 点，实例可覆盖
default_timeout_sec: 300     # 单次执行超时，5 分钟

icon: icon.svg               # 可选，前端卡片图标

# ============ 用户配置字段 ============
# 每个字段会在管家「创建实例」表单里渲染对应控件。
# secret 类型会自动 Fernet 加密落库 + sandbox 解密成明文跑完即销毁。
fields:
  - key: username
    label: 用户名
    type: string
    required: true
    description: 登录用的用户名
    placeholder: your-username

  - key: password
    label: 密码
    type: secret             # 加密存储，前端写后不可见
    required: true
    description: 登录用的密码;强烈建议与日常账号不同

  - key: random_delay_sec
    label: 随机延迟（秒）
    type: integer
    default: 60
    min: 0
    max: 3600
    description: |
      启动后随机 sleep 0~N 秒再签到，避开整点风控。
      设 0 = 立即开始（调试用）。

  # 更多字段示例（取消注释使用）:
  #
  # - key: site_url
  #   label: 站点 URL
  #   type: url
  #   schemes: [http, https]
  #   default: "https://example.com"
  #
  # - key: mode
  #   label: 签到模式
  #   type: select
  #   default: normal
  #   options:
  #     - { value: normal, label: 普通签到 }
  #     - { value: lucky,  label: 抽奖签到 }
  #
  # - key: extra_headers
  #   label: 额外请求头
  #   type: json
  #   default: "{}"

# ============ 运行时 ============
runtime:
  python_version: ">=3.10"
  isolated: true                          # true = 子进程隔离（推荐）
  env_passthrough:                        # 透传给子进程的环境变量（可选）
    - HTTP_PROXY
    - HTTPS_PROXY
    - NO_PROXY
  dependencies_file: requirements.txt     # 若存在，docker build 时 pip install
`;

// ============================================================
// main.py 模板
// ============================================================
export const MAIN_PY_TEMPLATE = `"""我的签到脚本 — 平台 sandbox_runner 协议适配。

平台契约:
- 入口:def run(config: dict, context: Any) -> RunResult
- config:用户在 web 配置的 fields 值（secret 已解密）
- context:run_id / instance_id / data_dir / trigger_type / attempt / logger
- 返回 RunResult(success=True/False, message=str, data=dict)
- 不要 sys.exit;不要 print('__RUN_RESULT__')，sandbox_runner 负责
- 日志用 context.logger.info / warning / error，自动汇集到 runs.stdout/stderr
- 失败截图 / 文件存到 context.data_dir（实例独立目录，跨执行持久）
- 业务可识别异常 → 抛自定义子类 → catch 后转 RunResult(success=False);
  未知异常 → 不 catch 让 sandbox_runner 标 error 状态
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any


# ====================================================================
# RunResult — 与 sandbox_runner 协议一致（本文件本地定义，无需 import 平台）
# ====================================================================
@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ====================================================================
# 业务异常 — 抛这些会被 catch 后转 RunResult.failure（非 error）
# ====================================================================
class MyScriptError(Exception):
    """脚本业务异常基类。"""


class LoginFailedError(MyScriptError):
    """登录失败，通常是凭证错。"""


class AlreadySignedError(MyScriptError):
    """今日已签 — 通常算 success，这里举例为可识别异常。"""


# ====================================================================
# 入口函数
# ====================================================================
def run(config: dict, context: Any) -> RunResult:
    """脚本入口。config / context 由平台传入。"""
    logger = context.logger

    # ============================================================
    # ⚠️ dry-run 短路 — 不要删除这段!!
    # ============================================================
    # 上传脚本时，平台会用 **空 config + run_id=0 + instance_id=0** 调一次 run()
    # 做"dry-run 自检"。run() 返 success=False → 上传被拒（HTTP 422）。
    # 删了这段 → 进来发现缺 username/password 就 return failure → 上传必失败。
    # dry-run 标识:context.run_id == 0 AND context.instance_id == 0
    # ============================================================
    if context.run_id == 0 and context.instance_id == 0:
        logger.info("dry-run 模式:跳过字段校验，返成功示范")
        return RunResult(success=True, message="dry-run OK · 模板已正常加载", data={"dry_run": True})

    # ---- 1. 取配置 ----
    username = config.get("username") or ""
    password = config.get("password") or ""
    random_delay = int(config.get("random_delay_sec") or 0)

    if not username or not password:
        return RunResult(success=False, message="缺少 username 或 password 配置")

    # ---- 2. 随机延迟（避开整点风控；manual 触发平台已强制跳过）----
    if random_delay > 0:
        delay = random.randint(0, random_delay)
        logger.info(f"随机延迟 {delay} 秒后开始")
        end_at = time.monotonic() + delay
        while time.monotonic() < end_at:
            time.sleep(min(5, end_at - time.monotonic()))

    # ---- 3. 实际签到逻辑 ----
    try:
        logger.info(f"开始签到 user={username}")

        # TODO: 在这里写你的签到逻辑
        #   - import httpx / requests / selenium 等
        #   - 登录 / 调签到接口 / 解析响应
        #   - 失败时 raise LoginFailedError("...") 或返回 RunResult(success=False)

        time.sleep(1)
        reward = "10 积分"
        logger.info(f"签到成功，获得 {reward}")
        return RunResult(success=True, message=f"签到成功，获得 {reward}", data={"reward": reward})

    except AlreadySignedError as e:
        return RunResult(success=True, message=str(e) or "今日已签到")
    except MyScriptError as e:
        logger.warning(f"签到失败:{e}")
        return RunResult(success=False, message=str(e))
    # 未知异常不 catch — 让 sandbox_runner 标 error 状态（带完整 stacktrace）


# ====================================================================
# 本地测试（不依赖平台）
# ====================================================================
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    class FakeContext:
        logger = logging.getLogger("local-test")
        data_dir = "/tmp"
        run_id = 0
        instance_id = 0
        trigger_type = "manual"
        attempt = 1

    result = run({"username": "demo", "password": "demo", "random_delay_sec": 0}, FakeContext())
    print(f"success={result.success} message={result.message} data={result.data}")
`;

// ============================================================
// requirements.txt 模板
// ============================================================
export const REQUIREMENTS_TEMPLATE = `# 你的 Python 依赖（每行一个，可指定版本），docker build 时自动 pip install
#
# 常用:
# httpx>=0.27         # 现代异步 HTTP 客户端（推荐）
# requests>=2.32      # 老牌同步 HTTP
# beautifulsoup4>=4   # HTML 解析
# lxml>=5             # 快速 XML / HTML 解析
#
# Selenium 类（只能在装了 Chrome 的节点跑）:
# selenium>=4
# seleniumbase>=4

httpx>=0.27
`;

// ============================================================
// README.md 模板
// ============================================================
export const README_TEMPLATE = `# 我的签到脚本

简短描述这是哪个站点的签到。

## 配置项

- **username** · 登录用户名
- **password** · 登录密码（自动加密存储）
- **random_delay_sec** · 启动后随机延迟，默认 60s

## 凭证获取方法

1. 打开 https://example.com 登录
2. ...

## 已知失败模式

- 凭证过期:重新填一遍密码即可
- ...

## 部署节点要求

- Python 3.10+
- 是否需要 Chrome? · 否（纯 HTTP）/ 是（需要 selenium 节点）
`;

// ============================================================
// icon.svg 模板（简单几何图标）
// ============================================================
export const ICON_SVG_TEMPLATE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
  <path d="m9 12 2 2 4-4"/>
</svg>
`;

// ============================================================
// 必备/可选文件清单（供 UploadDialog 显示 checklist）
// ============================================================
export interface RequiredFile {
  filename: string;
  required: boolean;
  hint: string;
}

export const SCRIPT_REQUIRED_FILES: RequiredFile[] = [
  { filename: 'manifest.yaml', required: true, hint: '元数据 + 配置字段定义（slug / name / version / fields / cron 等）' },
  { filename: 'main.py', required: true, hint: '实现 run(config, context) -> RunResult 入口（含 dry-run 短路）' },
  { filename: 'requirements.txt', required: false, hint: 'Python 依赖，docker build 时自动 pip install（无第三方依赖可省略）' },
  { filename: 'README.md', required: false, hint: '给真人看的使用文档，详情页会展示' },
  { filename: 'icon.svg', required: false, hint: '前端卡片图标（SVG，缺省用通用图标）' },
];

// ============================================================
// 生成模板 zip（前端下载）
// ============================================================
export async function buildTemplateZip(rootDirName = 'my-script-template'): Promise<Blob> {
  const zip = new JSZip();
  const root = zip.folder(rootDirName);
  if (!root) throw new Error('JSZip folder() returned null');
  root.file('manifest.yaml', MANIFEST_TEMPLATE);
  root.file('main.py', MAIN_PY_TEMPLATE);
  root.file('requirements.txt', REQUIREMENTS_TEMPLATE);
  root.file('README.md', README_TEMPLATE);
  root.file('icon.svg', ICON_SVG_TEMPLATE);
  return zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
