/**
 * <ScriptDevGuideSheet> — 脚本开发指南(右侧 Sheet)
 *
 * 在 UploadScriptDialog 顶部"📖 脚本开发指南"按钮触发,弹出右侧 Sheet
 * 显示完整开发协议。Sheet 三段式(header / scroll / footer)保证内容可滚 +
 * 关闭按钮永远可见。
 *
 * 内容来源:
 * - `进度/设计/后端架构.md` § 3(脚本插件接口规范)
 * - `backend/sandbox_runner.py`(实际契约)
 * - `scripts/coklw/main.py` / `scripts/jmcomic/main.py`(参考实现)
 */
import type { ReactNode } from 'react';
import { BookOpen, FileCode2, Package } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function ScriptDevGuideSheet({ open, onOpenChange }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-2xl"
      >
        <SheetHeader className="shrink-0 border-b border-border px-6 pb-4 pt-6">
          <SheetTitle className="flex items-center gap-2">
            <BookOpen className="size-5 text-primary" strokeWidth={1.75} />
            脚本开发指南
          </SheetTitle>
          <SheetDescription>
            写一个签到管家脚本需要知道的所有事 — 协议、字段、本地测试。
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5 text-sm leading-relaxed [scrollbar-gutter:stable]">
          {/* ============ 概览 ============ */}
          <Section title="📦 一个脚本是什么" icon={<Package className="size-4" />}>
            <p>
              一个"签到管家脚本"= 一个目录,根下含{' '}
              <Code>manifest.yaml</Code>(元数据 + 用户配置字段)+{' '}
              <Code>main.py</Code>(实现 <Code>run()</Code> 入口),可选
              {' '}<Code>requirements.txt</Code> / <Code>README.md</Code> /{' '}
              <Code>icon.svg</Code>。
            </p>
            <p>
              打成 zip 上传后,平台会:校验 manifest schema → dry-run 跑一次 →
              原子落盘到 <Code>scripts/&lt;slug&gt;/</Code> → 入库 → 出现在 /scripts 列表里。
              用户创建实例时填配置字段值 + 选节点 + 设 cron,平台到点自动调度。
            </p>
          </Section>

          {/* ============ 文件清单 ============ */}
          <Section title="📋 必备 / 可选文件" icon={<FileCode2 className="size-4" />}>
            <Table
              rows={[
                ['manifest.yaml', '✅ 必填', '元数据 + fields(实例配置项)+ runtime'],
                ['main.py', '✅ 必填', '实现 run(config, context) -> RunResult'],
                ['requirements.txt', '⚪ 可选', 'Python 依赖,docker build 时 pip install'],
                ['README.md', '⚪ 可选', '给真人看的使用文档'],
                ['icon.svg', '⚪ 可选', '前端卡片图标,缺省用通用图标'],
              ]}
            />
            <Callout type="warn">
              不允许:任何二进制文件(.pyc / .so / .exe / 大图等)、上传体积 &gt; 1 MiB、单文件
              &gt; 256 KiB、文件总数 &gt; 200。详见安全策略。
            </Callout>
          </Section>

          {/* ============ main.py 协议 ============ */}
          <Section title="🐍 main.py 协议">
            <p>
              必须实现一个 <Code>run(config, context) -&gt; RunResult</Code> 函数,平台子进程会
              加载本文件并调用它。
            </p>
            <Pre>{`from dataclasses import asdict, dataclass, field

@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def run(config: dict, context) -> RunResult:
    logger = context.logger
    username = config.get("username") or ""
    # ... 你的签到逻辑 ...
    return RunResult(
        success=True,
        message="签到成功,+10 积分",
        data={"reward": 10},
    )`}</Pre>
            <p>
              <strong>不要</strong> 调 <Code>sys.exit()</Code> 或{' '}
              <Code>print("__RUN_RESULT__...")</Code> — sandbox_runner 负责把返回值序列化。
            </p>
          </Section>

          {/* ============ dry-run 短路(必读!踩坑最多) ============ */}
          <Section title="🔍 dry-run 短路 · 上传前必读">
            <Callout type="warn">
              <strong>这是最常见的上传 422 失败原因。</strong>
              所有需要"用户配置项"才能跑的脚本(99% 签到都是)<strong>必须</strong>在{' '}
              <Code>run()</Code> 开头加 dry-run 短路。
            </Callout>
            <p>
              <strong>平台 dry-run 是什么:</strong>
              上传脚本时,平台用<strong>空 config + run_id=0 + instance_id=0</strong>
              调一次你的 <Code>run()</Code>,验证它能正常加载 + 执行 + 返{' '}
              <Code>RunResult</Code>。
            </p>
            <p>
              <strong>为什么会 422:</strong>
              sandbox_runner 的契约是:<Code>RunResult.success=False → exit_code=1</Code>。
              如果你的 <Code>run()</Code> 一进来就因为缺 <Code>username/password</Code>
              {' '}早 return <Code>RunResult(success=False, ...)</Code>,dry-run 退出码必然是 1,
              平台判失败 → 上传被拒。
            </p>
            <p>
              <strong>正确写法:</strong>
              在 <Code>run()</Code> 第一行加 dry-run 短路,真实跑时 run_id/instance_id 都是正数,
              不会走这个分支:
            </p>
            <Pre>{`def run(config: dict, context) -> RunResult:
    logger = context.logger

    # ⚠️ dry-run 短路 — 不要删!上传时平台用 0/0 跑一次验证脚本可加载
    if context.run_id == 0 and context.instance_id == 0:
        logger.info("dry-run 模式:跳过字段校验")
        return RunResult(success=True, message="dry-run OK")

    # 真实跑:正常校验配置
    username = config.get("username") or ""
    if not username:
        return RunResult(success=False, message="缺少 username")
    # ... 签到逻辑 ...`}</Pre>
            <Callout type="info">
              下载平台模板(添加脚本 → 📥 下载模板项目)的 <Code>main.py</Code>
              已经写好了这段,只要不删就 OK。
            </Callout>
          </Section>

          {/* ============ context 字段 ============ */}
          <Section title="📥 context 字段">
            <Table
              rows={[
                ['context.logger', 'logging.Logger', '用它打日志,自动汇集到 runs.stdout/stderr'],
                ['context.data_dir', 'str', '本实例独立持久目录,失败截图 / cookies 缓存放这'],
                ['context.run_id', 'int', '当前 run 的 ID'],
                ['context.instance_id', 'int', '当前实例 ID'],
                ['context.trigger_type', 'str', '"manual" / "scheduled" / "retry"'],
                ['context.attempt', 'int', '第几次尝试(retry 时 ≥ 2)'],
              ]}
            />
          </Section>

          {/* ============ 异常处理 ============ */}
          <Section title="⚠️ 异常处理">
            <p>
              <strong>已知业务异常</strong> · catch 后返回{' '}
              <Code>RunResult(success=False, message=...)</Code> →平台标 <Code>failure</Code>:
            </p>
            <Pre>{`class LoginFailedError(Exception):
    pass

try:
    do_login()
except LoginFailedError as e:
    return RunResult(success=False, message=f"登录失败: {e}")`}</Pre>
            <p>
              <strong>未知异常</strong> · 不要 catch,让 sandbox_runner 自动捕获 → 标{' '}
              <Code>error</Code>(带完整 stacktrace 到 runs.stderr)。
            </p>
          </Section>

          {/* ============ manifest.yaml 必填字段 ============ */}
          <Section title="📄 manifest.yaml 必填字段">
            <Table
              rows={[
                ['slug', 'string', '唯一标识,必须等于目录名,正则 [a-z][a-z0-9-]{0,40}'],
                ['name', 'string', '显示名,长度 1-128(可中文)'],
                ['version', 'string', 'SemVer,如 1.0.0 / 1.0.0-rc1'],
              ]}
            />
            <p className="mt-3">推荐填:</p>
            <Table
              rows={[
                ['description', 'multiline', 'markdown 说明(显示在脚本详情页)'],
                ['author', 'string', '作者名'],
                ['homepage', 'url', '项目主页 / 源码地址'],
                ['default_cron', 'cron', '默认 cron 表达式(实例可覆盖)'],
                ['default_timeout_sec', 'int', '默认超时,1-86400 秒'],
                ['icon', 'string', '图标文件名,默认 "icon.svg"'],
              ]}
            />
          </Section>

          {/* ============ field 类型 ============ */}
          <Section title="🔧 字段类型(11 种)">
            <p>
              每个 <Code>fields[*]</Code> 在"创建实例"表单里渲染对应控件,平台帮你做完整校验。
            </p>
            <Table
              header={['type', '渲染', '特有属性']}
              rows={[
                ['string', '单行 Input', 'min_length / max_length / pattern'],
                ['secret', '密文 Input + 👁', '自动 Fernet 加密落库'],
                ['integer', '数字 Input', 'min / max / step'],
                ['boolean', 'Switch', '—'],
                ['select', '下拉单选', 'options[].{value, label, description}'],
                ['multiselect', '下拉多选', 'options + min_items / max_items'],
                ['multiline', '多行 Textarea', 'rows(1-50)'],
                ['cron', 'cron 输入 + 校验', '后端 APScheduler 校验合法性'],
                ['url', 'URL Input', 'schemes (如 [http, https])'],
                ['json', 'JSON Editor', 'schema(JSON Schema 字符串)'],
              ]}
            />
            <Callout type="info">
              所有字段还可以传:<Code>required</Code> / <Code>default</Code> /{' '}
              <Code>description</Code> / <Code>placeholder</Code> / <Code>group</Code>(分组显示)。
            </Callout>
          </Section>

          {/* ============ 本地测试 ============ */}
          <Section title="🧪 本地测试">
            <p>模板的 main.py 末尾自带 <Code>if __name__ == "__main__":</Code> 测试块:</p>
            <Pre>{`cd my-script-template/
python main.py`}</Pre>
            <p>
              输出 <Code>=== RESULT ===</Code> + RunResult 字段即说明你的 run() 能正常返回。
              上传后平台的 dry-run 跑的是同一个 main.py,所以本地能跑 = 上传几乎必过。
            </p>
            <p>
              若需要更真实测试(sandbox_runner 完整契约),可以本地直接调:
            </p>
            <Pre>{`echo '{"config":{"username":"demo","password":"demo"},"context":{"run_id":0,"data_dir":"/tmp","trigger_type":"manual"}}' \\
  | python ../path/to/sandbox_runner.py`}</Pre>
          </Section>

          {/* ============ 部署节点要求 ============ */}
          <Section title="🌐 部署节点要求">
            <p>
              脚本默认在 <strong>主面板节点</strong>(local)跑。如果需要特殊环境(Chrome /
              特殊 IP / 大内存),创建实例时选远程 agent 节点。
            </p>
            <Table
              header={['脚本类型', '推荐节点', '原因']}
              rows={[
                ['纯 HTTP(httpx/requests)', 'local 或任意 agent', '依赖少'],
                ['Selenium / 浏览器自动化', 'agent 节点 + 装 Chrome', '主面板 Docker 容器无 Chrome'],
                ['特定地区 IP 限制', 'IP 匹配的 agent 节点', '反爬 / 地区限制'],
                ['大内存(> 1 GiB)', '配置足够的 agent 节点', '主面板默认 2 GiB 共享给其它服务'],
              ]}
            />
            <Callout type="warn">
              Selenium 脚本必须在 Linux agent 节点 + root 权限 + 自动装 xvfb / Chrome /
              chromedriver。manifest description 里写清这些前置条件,避免用户绑错节点。
            </Callout>
          </Section>

          {/* ============ 快速参考 ============ */}
          <Section title="📚 完整示例参考">
            <p>已上线的脚本可作参考(主面板源码 <Code>scripts/</Code>):</p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <Code>scripts/coklw/</Code> — 最简纯 httpx 版(WordPress 站点 cookie 签到)
              </li>
              <li>
                <Code>scripts/ptfans/</Code> — NexusPHP cookie 签到(GET 接口)
              </li>
              <li>
                <Code>scripts/jmcomic/</Code> — selenium + 账密版(过 Cloudflare Turnstile,
                cookies 复用 + 智能重试)
              </li>
            </ul>
          </Section>
        </div>

        <div className="shrink-0 border-t border-border bg-background px-6 py-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto block"
            onClick={() => onOpenChange(false)}
          >
            关闭
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ============================================================
// 内部小组件
// ============================================================
function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <h3 className="flex items-center gap-1.5 text-base font-semibold text-foreground">
        {icon}
        {title}
      </h3>
      <div className="space-y-2 text-muted-foreground">{children}</div>
    </section>
  );
}

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12.5px] text-foreground">
      {children}
    </code>
  );
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-border bg-card/40 p-3 font-mono text-[11.5px] leading-snug text-foreground">
      {children}
    </pre>
  );
}

function Table({
  header,
  rows,
}: {
  header?: string[];
  rows: (string | ReactNode)[][];
}) {
  const defaultHeader = header || ['字段', '类型', '说明'];
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            {defaultHeader.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr
              key={i}
              className="border-b border-border/40 last:border-b-0 hover:bg-muted/20"
            >
              {cells.map((c, j) => (
                <td
                  key={j}
                  className={
                    j === 0
                      ? 'px-3 py-2 font-mono text-[11.5px] text-foreground'
                      : j === 1
                        ? 'px-3 py-2 text-foreground'
                        : 'px-3 py-2 text-muted-foreground'
                  }
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Callout({
  type,
  children,
}: {
  type: 'info' | 'warn';
  children: ReactNode;
}) {
  const cls =
    type === 'warn'
      ? 'border-warning/30 bg-warning/10 text-foreground'
      : 'border-primary/30 bg-primary/10 text-foreground';
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${cls}`}>{children}</div>
  );
}

export default ScriptDevGuideSheet;
