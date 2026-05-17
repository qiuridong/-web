/**
 * <LogViewer> — xterm + SSE 实时日志查看器
 *
 * 设计契约:
 *   - § 3.8 实时日志查看器(xterm.js + SSE)
 *   - § 6.3 useLogStream hook
 *   - § 8 xterm 主题与 CSS vars 同步
 *
 * 工具栏:暂停/恢复 / 全屏(浏览器 fullscreen API)/ 搜索 / 清屏 / 导出 .log
 *
 * 实现要点:
 *   - 用 hooks/runs.ts 的 useLogStream 提供 onStdout/onStderr 回调,直接写 xterm
 *     避免大缓冲数组在 React state 中反复 setState 拖性能
 *   - autoFollow:用户滚到底部时自动跟随;手动滚上后停止跟随,显示"⬇ 跳回底部"按钮
 *   - stderr 行用 ANSI 31m 红色显示
 *   - 主题色取 :root 的 CSS var(运行时算 getComputedStyle,跟随主题切换会脱钩,
 *     如需 hot-switch 需监听 next-themes;v1 取连接时一次)
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import {
  CircleAlert,
  CircleCheckBig,
  CirclePause,
  CirclePlay,
  Download,
  Eraser,
  Loader2,
  Maximize2,
  Minimize2,
  Search,
} from 'lucide-react';
import { Terminal, type ITheme } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import { WebLinksAddon } from '@xterm/addon-web-links';

import '@xterm/xterm/css/xterm.css';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useLogStream, type LogStreamStatus, type RunStatus } from '@/api/hooks/runs';
import { cn } from '@/lib/utils';

export interface LogViewerProps {
  runId: number | undefined;
  /** 初始日志(后端 GET /runs/{id} 返回的 stdout 等)— 可选,SSE 端点也会回放 */
  initialStdout?: string | null;
  initialStderr?: string | null;
  /** 高度类名,默认 h-[480px] */
  heightClassName?: string;
  className?: string;
  /** 自动跟随 — 默认 true;用户滚动后中断 */
  autoFollow?: boolean;
}

const ANSI_RED = '\x1b[31m';
const ANSI_RESET = '\x1b[0m';
const ANSI_DIM = '\x1b[2m';

interface XtermBundle {
  term: Terminal;
  fit: FitAddon;
  search: SearchAddon;
}

/**
 * 从当前 :root CSS vars 读取主题色,产出 xterm ITheme。
 *
 * 与 index.css 的 CSS var 名一致;若用户在 Settings → 外观切了主题或主题色,
 * 这里能即时读到最新值。
 */
function readTermTheme(): ITheme {
  const css = getComputedStyle(document.documentElement);
  const v = (k: string, fallback: string): string => {
    const x = css.getPropertyValue(k).trim();
    return x || fallback;
  };
  return {
    background: v('--background', '#0d0f14'),
    foreground: v('--foreground', '#e5e7eb'),
    cursor: v('--primary', '#7c8cf2'),
    cursorAccent: v('--background', '#0d0f14'),
    selectionBackground: 'rgba(120,120,180,0.35)',
    black: '#0b0e14',
    brightBlack: '#5c6370',
    red: '#ef4444',
    brightRed: '#f87171',
    green: '#10b981',
    brightGreen: '#34d399',
    yellow: '#f59e0b',
    brightYellow: '#fbbf24',
    blue: '#3b82f6',
    brightBlue: '#60a5fa',
    magenta: '#a855f7',
    brightMagenta: '#c084fc',
    cyan: '#06b6d4',
    brightCyan: '#22d3ee',
    white: '#d1d5db',
    brightWhite: '#f9fafb',
  };
}

function buildTerminal(): XtermBundle {
  const term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'bar',
    fontSize: 13,
    lineHeight: 1.35,
    fontFamily:
      'JetBrains Mono Variable, JetBrains Mono, Menlo, Consolas, monospace',
    scrollback: 10000,
    convertEol: true,
    allowTransparency: true,
    theme: readTermTheme(),
  });
  const fit = new FitAddon();
  const search = new SearchAddon();
  const links = new WebLinksAddon();
  term.loadAddon(fit);
  term.loadAddon(search);
  term.loadAddon(links);
  return { term, fit, search };
}

function statusToLabel(status: RunStatus): string {
  switch (status) {
    case 'pending':
      return '等待中';
    case 'running':
      return '运行中';
    case 'success':
      return '成功';
    case 'failure':
      return '失败';
    case 'error':
      return '错误';
    case 'timeout':
      return '超时';
    case 'cancelled':
      return '已取消';
    default:
      return status;
  }
}

function statusToColor(status: RunStatus): string {
  switch (status) {
    case 'success':
      return 'text-success';
    case 'failure':
    case 'error':
      return 'text-danger';
    case 'timeout':
      return 'text-warning';
    case 'running':
    case 'pending':
      return 'text-info';
    default:
      return 'text-muted-foreground';
  }
}

export function LogViewer({
  runId,
  initialStdout,
  initialStderr,
  heightClassName = 'h-[480px]',
  className,
  autoFollow = true,
}: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const bundleRef = useRef<XtermBundle | null>(null);
  const initialWrittenRef = useRef<Set<number>>(new Set());

  const [paused, setPaused] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [following, setFollowing] = useState(autoFollow);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchValue, setSearchValue] = useState('');

  // 主题切换:next-themes 提供 resolvedTheme(light|dark|undefined)
  const { resolvedTheme } = useTheme();

  // 初始化 xterm(一次)
  useEffect(() => {
    if (!containerRef.current) return;
    if (bundleRef.current) return;

    const bundle = buildTerminal();
    bundle.term.open(containerRef.current);
    bundleRef.current = bundle;
    try {
      bundle.fit.fit();
    } catch {
      // 初次 layout 0px 时可能抛;下个 frame 再试
    }

    // ResizeObserver:容器尺寸变化时 fit
    const ro = new ResizeObserver(() => {
      try {
        bundle.fit.fit();
      } catch {
        // ignore
      }
    });
    ro.observe(containerRef.current);

    // 用户滚动:判断是否仍贴底,贴底则跟随,否则停止
    bundle.term.onScroll(() => {
      const view = bundle.term.buffer.active.viewportY;
      const base = bundle.term.buffer.active.baseY;
      setFollowing(view >= base - 1);
    });

    return () => {
      ro.disconnect();
      bundle.term.dispose();
      bundleRef.current = null;
    };
  }, []);

  // 主题热刷:resolvedTheme 变化 → 把当前 CSS var 重新取一次写回 term.options.theme
  // 注:next-themes 在写 html.className 后才会触发本 effect,readTermTheme() 此刻读到的已是新色
  useEffect(() => {
    const bundle = bundleRef.current;
    if (!bundle) return;
    // 用 rAF 等浏览器 commit 完新 class,再读 computedStyle,避免取到旧色
    const id = requestAnimationFrame(() => {
      try {
        bundle.term.options.theme = readTermTheme();
      } catch {
        // ignore — xterm 偶尔在 dispose 边缘抛
      }
    });
    return () => cancelAnimationFrame(id);
  }, [resolvedTheme]);

  // 写入 initialStdout / initialStderr(在 runId 变化时一次性)
  useEffect(() => {
    const bundle = bundleRef.current;
    if (!bundle) return;
    if (runId === undefined || initialWrittenRef.current.has(runId)) return;
    initialWrittenRef.current.add(runId);
    bundle.term.clear();
    if (initialStdout) {
      bundle.term.write(initialStdout.endsWith('\n') ? initialStdout : initialStdout + '\r\n');
    }
    if (initialStderr) {
      const lines = initialStderr.split(/\r?\n/);
      for (const line of lines) {
        if (line) {
          bundle.term.write(`${ANSI_RED}${line}${ANSI_RESET}\r\n`);
        }
      }
    }
  }, [runId, initialStdout, initialStderr]);

  // SSE
  const stream = useLogStream(runId, {
    auto: true,
    onStdout: (line) => {
      const bundle = bundleRef.current;
      if (!bundle || paused) return;
      bundle.term.write(line + '\r\n');
      if (following) bundle.term.scrollToBottom();
    },
    onStderr: (line) => {
      const bundle = bundleRef.current;
      if (!bundle || paused) return;
      bundle.term.write(`${ANSI_RED}${line}${ANSI_RESET}\r\n`);
      if (following) bundle.term.scrollToBottom();
    },
    onStatus: () => {
      // status 仅展示在 footer,不写终端
    },
    onEnd: () => {
      const bundle = bundleRef.current;
      if (bundle) {
        bundle.term.write(`\r\n${ANSI_DIM}— 日志流已结束 —${ANSI_RESET}\r\n`);
      }
    },
  });

  // 全屏切换
  useEffect(() => {
    const handler = () => {
      setFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  function toggleFullscreen() {
    if (!wrapRef.current) return;
    if (!document.fullscreenElement) {
      void wrapRef.current.requestFullscreen?.();
    } else {
      void document.exitFullscreen?.();
    }
  }

  function handleClear() {
    bundleRef.current?.term.clear();
  }

  function handleExport() {
    const bundle = bundleRef.current;
    if (!bundle) return;
    const lines: string[] = [];
    const buf = bundle.term.buffer.active;
    for (let i = 0; i < buf.length; i += 1) {
      const line = buf.getLine(i);
      if (line) lines.push(line.translateToString(true));
    }
    const text = lines.join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-${runId ?? 'unknown'}.log`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 1000);
  }

  function handleSearchNext(rev = false) {
    const bundle = bundleRef.current;
    if (!bundle || !searchValue) return;
    if (rev) bundle.search.findPrevious(searchValue);
    else bundle.search.findNext(searchValue);
  }

  function togglePause() {
    if (paused) {
      // resume
      stream.resume();
      setPaused(false);
    } else {
      stream.pause();
      setPaused(true);
    }
  }

  function scrollBottom() {
    setFollowing(true);
    bundleRef.current?.term.scrollToBottom();
  }

  const statusInfo = useMemo<{
    status: RunStatus | 'unknown';
    exit?: number | null;
    duration?: number | null;
  }>(() => {
    const s: LogStreamStatus | null = stream.status;
    return {
      status: s?.status ?? 'unknown',
      exit: s?.exit_code,
      duration: s?.duration_ms,
    };
  }, [stream.status]);

  const connecting = stream.state === 'connecting';
  const closed = stream.state === 'closed';

  return (
    <div
      ref={wrapRef}
      className={cn(
        'flex w-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xs',
        fullscreen && 'rounded-none',
        className,
      )}
    >
      {/* 工具栏 */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-muted/30 px-3 text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {connecting ? (
            <>
              <Loader2 className="size-3 animate-spin" strokeWidth={1.75} />
              <span>连接中…</span>
            </>
          ) : statusInfo.status === 'unknown' ? (
            <>
              <span className="inline-block size-2 rounded-full bg-muted-foreground/40" />
              <span>等待状态</span>
            </>
          ) : (
            <>
              <span
                className={cn(
                  'inline-block size-2 rounded-full bg-current',
                  statusToColor(statusInfo.status as RunStatus),
                  (statusInfo.status === 'running' || statusInfo.status === 'pending') &&
                    'dot-pulse',
                )}
              />
              <span className={cn('font-medium', statusToColor(statusInfo.status as RunStatus))}>
                {statusToLabel(statusInfo.status as RunStatus)}
              </span>
            </>
          )}
          {statusInfo.exit !== null && statusInfo.exit !== undefined ? (
            <span className="text-muted-foreground/60 tabular-nums">
              · exit {statusInfo.exit}
            </span>
          ) : null}
          {statusInfo.duration ? (
            <span className="text-muted-foreground/60 tabular-nums">
              · {Math.round(statusInfo.duration)} ms
            </span>
          ) : null}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <Popover open={searchOpen} onOpenChange={setSearchOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                aria-label="搜索"
                title="搜索 (Ctrl+F)"
              >
                <Search className="size-3.5" strokeWidth={1.75} />
                搜索
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-72 p-2">
              <div className="flex items-center gap-1">
                <Input
                  value={searchValue}
                  onChange={(e) => setSearchValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleSearchNext(e.shiftKey);
                    }
                  }}
                  placeholder="搜索关键字"
                  className="h-8 text-sm"
                  autoFocus
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 px-2"
                  onClick={() => handleSearchNext(true)}
                  disabled={!searchValue}
                >
                  ↑
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 px-2"
                  onClick={() => handleSearchNext(false)}
                  disabled={!searchValue}
                >
                  ↓
                </Button>
              </div>
              <p className="mt-1.5 text-[10px] text-muted-foreground">
                回车下一个 · Shift+回车 上一个
              </p>
            </PopoverContent>
          </Popover>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={togglePause}
            disabled={closed}
            aria-label={paused ? '恢复' : '暂停'}
            title={paused ? '恢复' : '暂停'}
          >
            {paused ? (
              <CirclePlay className="size-3.5" strokeWidth={1.75} />
            ) : (
              <CirclePause className="size-3.5" strokeWidth={1.75} />
            )}
            {paused ? '恢复' : '暂停'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={handleClear}
            aria-label="清屏"
            title="清屏(不影响后端日志)"
          >
            <Eraser className="size-3.5" strokeWidth={1.75} />
            清屏
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={handleExport}
            aria-label="导出"
            title="下载 .log"
          >
            <Download className="size-3.5" strokeWidth={1.75} />
            导出
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={toggleFullscreen}
            aria-label={fullscreen ? '退出全屏' : '全屏'}
            title={fullscreen ? '退出全屏' : '全屏'}
          >
            {fullscreen ? (
              <Minimize2 className="size-3.5" strokeWidth={1.75} />
            ) : (
              <Maximize2 className="size-3.5" strokeWidth={1.75} />
            )}
          </Button>
        </div>
      </div>

      {/* xterm 容器 */}
      <div className={cn('relative w-full', fullscreen ? 'flex-1' : heightClassName)}>
        <div ref={containerRef} className="absolute inset-0 px-2 pt-2" />
        {!following ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="absolute bottom-3 right-3 z-10 h-7 gap-1 text-xs shadow-md"
            onClick={scrollBottom}
          >
            ⬇ 跳回底部
          </Button>
        ) : null}
        {runId === undefined ? (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 text-sm text-muted-foreground">
            选中一条 run 以加载日志流
          </div>
        ) : null}
      </div>

      {/* 底部状态条 */}
      <div className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-muted/30 px-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-2 tabular-nums">
          {stream.state === 'open' ? (
            <CircleCheckBig className="size-3 text-success" strokeWidth={1.75} />
          ) : stream.state === 'error' ? (
            <CircleAlert className="size-3 text-danger" strokeWidth={1.75} />
          ) : null}
          连接状态:{stream.state}
        </span>
        <span className="tabular-nums">
          缓存 {stream.lines.length} 行 · run #{runId ?? '-'}
        </span>
      </div>
    </div>
  );
}

export default LogViewer;
