/**
 * 节点管理页 — /nodes
 *
 * MVP-1 远程 agent 架构:
 *   - 列出所有节点(local + 远程 agent)
 *   - 添加节点 → 返回一次性 token + 一键安装命令
 *   - 启用/禁用 + 重新生成 token + 删除(非 local)
 *
 * 设计稿:`进度/设计/远程VPS脚本执行调研.md` § 9.1
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Server,
  Plus,
  Copy,
  RefreshCw,
  Trash2,
  Power,
  PowerOff,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Info,
  Terminal,
  ScrollText,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { PageHeader } from '@/components/common/PageHeader';
import { EmptyState } from '@/components/common/EmptyState';
import {
  useNodes,
  useNode,
  useCreateNode,
  useUpdateNode,
  useDeleteNode,
  useRegenerateNodeToken,
  useUninstallNodeScript,
  type NodeListItem,
} from '@/api/hooks/nodes';
import { formatRelative } from '@/lib/format';

// 主面板地址 — 用于生成 install 命令(运行时从 window.location 拿 origin)
function getMasterUrl(): string {
  if (typeof window !== 'undefined') return window.location.origin;
  return 'https://jb.aijiaxia.cc';
}

// ============================================================
// Token / 安装信息展示 Dialog
// - mode='fresh':新建/重新生成 token 后弹,显示真 token + 一次性警告
// - mode='replay':节点列表点 "查看安装信息" 弹,显示 placeholder + 说明
// ============================================================
function TokenDisplayDialog({
  open,
  onOpenChange,
  token,
  nodeSlug,
  mode = 'fresh',
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** mode=fresh 时传真 token;mode=replay 时传 null,显示 placeholder */
  token: string | null;
  nodeSlug: string;
  mode?: 'fresh' | 'replay';
}) {
  const master = getMasterUrl();
  const isFresh = mode === 'fresh' && token;
  const tokenForCmd = isFresh ? (token as string) : '<YOUR_TOKEN_HERE>';
  const installCmd = `sudo bash install.sh \\
  --master ${master} \\
  --token ${tokenForCmd} \\
  --node-slug ${nodeSlug}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isFresh ? (
              <>
                <CheckCircle2 size={18} className="text-success" />
                节点已创建 / Token 已生成
              </>
            ) : (
              <>
                <Info size={18} className="text-primary" />
                节点 「{nodeSlug}」 安装信息
              </>
            )}
          </DialogTitle>
          <DialogDescription>
            {isFresh ? (
              <span className="flex items-center gap-1.5 text-danger">
                <AlertTriangle size={14} />
                token 仅此一次显示,关闭后无法再查看。请立刻复制保存,丢失后只能重新生成。
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Info size={14} />
                Token 创建/重新生成时一次性显示,已无法找回。如需新 token 请点节点卡片的「重新生成」按钮(旧 token 立即失效)。
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Token(仅 fresh 模式显示) */}
          {isFresh && (
            <div>
              <Label className="text-xs text-muted-foreground">Node Token</Label>
              <div className="mt-1 flex gap-2">
                <Input
                  value={token as string}
                  readOnly
                  className="font-mono text-xs"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    void navigator.clipboard.writeText(token as string);
                    toast.success('Token 已复制');
                  }}
                  title="复制"
                >
                  <Copy size={14} />
                </Button>
              </div>
            </div>
          )}

          {/* 一键安装命令 */}
          <div>
            <Label className="text-xs text-muted-foreground">
              在目标 VPS 上执行(install.sh 在 agent/ 目录)
            </Label>
            <div className="mt-1 space-y-2">
              <Textarea
                value={installCmd}
                readOnly
                rows={4}
                className="font-mono text-xs leading-relaxed"
                onFocus={(e) => e.currentTarget.select()}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void navigator.clipboard.writeText(installCmd);
                  toast.success('安装命令已复制');
                }}
              >
                <Copy size={14} className="mr-2" />
                复制安装命令
              </Button>
            </div>
          </div>

          {/* 安装步骤简要 */}
          <div className="rounded-md border border-border bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground">
            <p className="mb-1 font-medium text-foreground">部署步骤:</p>
            <ol className="list-decimal space-y-0.5 pl-4">
              <li>把 agent/ 目录 + backend/sandbox_runner.py scp 到目标 VPS</li>
              <li>SSH 到目标 VPS,执行上面那条 install.sh 命令(需 root)</li>
              <li>同步脚本到 agent:scp /opt/signin-panel/scripts/{'<slug>'} 到 agent 的 scripts_dir</li>
              <li>journalctl -u signin-agent -f 看 agent 启动日志,本页节点状态会变成「在线」</li>
              <li>创建实例时下拉选这个节点,签到任务就会派发到这台 VPS 跑</li>
            </ol>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>已保存 token,关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// 添加节点 Dialog
// ============================================================
function AddNodeDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (token: string, slug: string) => void;
}) {
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const { mutateAsync: create, isPending } = useCreateNode();

  async function handleSubmit() {
    if (!slug.trim()) {
      toast.error('请填写 slug');
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]{0,62}$/.test(slug)) {
      toast.error('slug 格式:小写字母/数字开头,只含小写字母/数字/连字符');
      return;
    }
    try {
      const resp = await create({
        slug: slug.trim(),
        name: name.trim() || null,
        description: description.trim() || null,
      });
      onCreated(resp.token, resp.node.slug);
      onOpenChange(false);
      // 清空表单
      setSlug('');
      setName('');
      setDescription('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`创建失败:${msg}`);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>添加节点</DialogTitle>
          <DialogDescription>
            注册一个新的远程节点,主面板会生成一次性 token 用于 agent 鉴权
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="slug">
              Slug <span className="text-danger">*</span>
            </Label>
            <Input
              id="slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="vps-jm"
              className="font-mono"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              唯一标识,只能小写字母/数字/连字符,如 <code>vps-jm</code>
            </p>
          </div>

          <div>
            <Label htmlFor="name">显示名</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VPS-JM(原 JMComic 节点)"
            />
          </div>

          <div>
            <Label htmlFor="description">描述</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="如:美西节点 - Chrome/Xvfb 完整环境,跑 selenium 类脚本"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Plus size={14} className="mr-2" />}
            {isPending ? '创建中…' : '创建 + 生成 Token'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// 节点已部署脚本管理 Dialog
// ============================================================
function NodeScriptsDialog({
  open,
  onOpenChange,
  node,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  node: NodeListItem;
}) {
  const { data: detail, isLoading } = useNode(open ? node.id : undefined);
  const { mutate: uninstall, isPending } = useUninstallNodeScript();
  const deployed = detail?.deployed_scripts ?? {};
  const pendingDelete = detail?.pending_actions?.delete ?? [];
  const slugs = Object.keys(deployed).sort();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScrollText size={18} className="text-primary" />
            「{node.name || node.slug}」上的已部署脚本
          </DialogTitle>
          <DialogDescription>
            agent 实际报告的本地脚本。删除会下发指令,agent 下次 poll(最长 30s)时删本地{' '}
            <code>scripts/&lt;slug&gt;/</code> 并回报。
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 size={14} className="animate-spin" />
            加载中…
          </div>
        ) : slugs.length === 0 ? (
          <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            该节点暂无 agent 上报的已部署脚本。
            {pendingDelete.length > 0 && (
              <div className="mt-1 text-warning">
                (有待删除指令在途:{pendingDelete.join(', ')})
              </div>
            )}
          </div>
        ) : (
          <ul className="max-h-[50vh] space-y-2 overflow-y-auto">
            {slugs.map((slug) => {
              const info = deployed[slug] || {};
              const isPendingDel = pendingDelete.includes(slug);
              return (
                <li
                  key={slug}
                  className="flex items-center justify-between gap-2 rounded-md border border-border p-2.5"
                >
                  <div className="min-w-0">
                    <code className="text-sm font-medium">{slug}</code>
                    <div className="truncate text-[11px] text-muted-foreground">
                      {info.sha256 ? `sha256 ${String(info.sha256).slice(0, 12)}… · ` : ''}
                      {info.deployed_at ? `部署于 ${formatRelative(info.deployed_at)}` : ''}
                    </div>
                  </div>
                  {isPendingDel ? (
                    <Badge
                      variant="outline"
                      className="shrink-0 border-warning/30 bg-warning/10 text-warning"
                    >
                      待 agent 删除
                    </Badge>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isPending}
                      className="shrink-0 border-danger/30 text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() => uninstall({ nodeId: node.id, slug })}
                    >
                      <Trash2 size={13} className="mr-1.5" />
                      删除
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// 节点卡片
// ============================================================
function NodeCard({ node }: { node: NodeListItem }) {
  const { mutateAsync: update } = useUpdateNode();
  const { mutateAsync: regenerate, isPending: regenPending } = useRegenerateNodeToken();
  const { mutateAsync: del, isPending: delPending } = useDeleteNode();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [tokenShow, setTokenShow] = useState<string | null>(null);
  const [showInstallInfo, setShowInstallInfo] = useState(false);
  const [showScripts, setShowScripts] = useState(false);

  async function handleToggleEnabled() {
    try {
      await update({ id: node.id, payload: { enabled: !node.enabled } });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`更新失败:${msg}`);
    }
  }

  async function handleRegenerate() {
    setConfirmRegen(false);
    try {
      const resp = await regenerate(node.id);
      setTokenShow(resp.token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`重新生成失败:${msg}`);
    }
  }

  async function handleDelete() {
    setConfirmDelete(false);
    try {
      await del(node.id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`删除失败:${msg}`);
    }
  }

  return (
    <>
      <div className="rounded-lg border border-border bg-card p-4 shadow-sm transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div
              className={[
                'flex size-10 shrink-0 items-center justify-center rounded-lg',
                node.is_local
                  ? 'bg-primary/15 text-primary'
                  : node.online
                    ? 'bg-success/15 text-success'
                    : 'bg-muted text-muted-foreground',
              ].join(' ')}
            >
              <Server size={18} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="truncate text-base font-semibold">{node.name || node.slug}</h3>
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{node.slug}</code>
                {node.is_local && (
                  <Badge variant="secondary" className="text-[10px]">
                    LOCAL
                  </Badge>
                )}
                {!node.enabled && (
                  <Badge variant="destructive" className="text-[10px]">
                    已禁用
                  </Badge>
                )}
              </div>
              {node.description && (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{node.description}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                {node.is_local ? (
                  <span className="flex items-center gap-1 text-primary">
                    <CheckCircle2 size={12} />
                    本地节点(主面板自身)
                  </span>
                ) : node.online ? (
                  <span className="flex items-center gap-1 text-success">
                    <CheckCircle2 size={12} />
                    在线
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <XCircle size={12} />
                    离线
                  </span>
                )}
                {node.version && <span>v{node.version}</span>}
                {node.last_seen_at && (
                  <span>上次心跳:{formatRelative(node.last_seen_at)}</span>
                )}
              </div>
            </div>
          </div>

          {/* 操作(shadcn Tooltip 替代原生 title)*/}
          {!node.is_local && (
            <div className="flex shrink-0 gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowInstallInfo(true)}
                    className="text-primary hover:text-primary hover:bg-primary/10"
                  >
                    <Terminal size={14} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  查看安装命令(install.sh)
                </TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowScripts(true)}
                    className="hover:bg-muted"
                  >
                    <ScrollText size={14} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>管理已部署脚本(查看 / 删除)</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleToggleEnabled}
                    className={node.enabled ? 'hover:bg-warning/10' : 'hover:bg-success/10'}
                  >
                    {node.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {node.enabled ? '禁用节点(暂停接收任务)' : '启用节点(恢复接收任务)'}
                </TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setConfirmRegen(true)}
                    disabled={regenPending}
                    className="hover:bg-muted"
                  >
                    <RefreshCw size={14} className={regenPending ? 'animate-spin' : ''} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  重新生成 Token(旧 token 立即失效,需更新到 agent config.yaml)
                </TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setConfirmDelete(true)}
                    disabled={delPending}
                    className="text-danger hover:text-danger hover:bg-danger/10"
                  >
                    <Trash2 size={14} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  删除节点(有实例关联会拒绝)
                </TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
      </div>

      {/* Regen 确认 */}
      <AlertDialog open={confirmRegen} onOpenChange={setConfirmRegen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>重新生成 Token?</AlertDialogTitle>
            <AlertDialogDescription>
              旧 token 立即失效,目前在线的 agent 会被踢下线。重新生成后需要把新 token 更新到 agent 的{' '}
              <code>/etc/signin-agent/config.yaml</code> 并 restart。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerate}>确认重新生成</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete 确认 */}
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除节点 {node.slug}?</AlertDialogTitle>
            <AlertDialogDescription>
              如果有实例关联此节点,后端会返 409,删除将失败。请先把实例迁移到其它节点。
              <br />
              <strong>本操作不可撤销。</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-danger text-danger-foreground">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 新 token 展示(regenerate 后) */}
      {tokenShow && (
        <TokenDisplayDialog
          open={!!tokenShow}
          onOpenChange={(v) => !v && setTokenShow(null)}
          token={tokenShow}
          nodeSlug={node.slug}
          mode="fresh"
        />
      )}

      {/* 查看安装信息(replay 模式,无 token) */}
      <TokenDisplayDialog
        open={showInstallInfo}
        onOpenChange={setShowInstallInfo}
        token={null}
        nodeSlug={node.slug}
        mode="replay"
      />

      {/* 管理已部署脚本(查看 / 删除) */}
      <NodeScriptsDialog open={showScripts} onOpenChange={setShowScripts} node={node} />
    </>
  );
}

// ============================================================
// NodeList 主页
// ============================================================
export function NodeList() {
  const { data, isLoading, isError, error, refetch } = useNodes();
  const [addOpen, setAddOpen] = useState(false);
  const [newToken, setNewToken] = useState<{ token: string; slug: string } | null>(null);

  const nodes = data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="节点管理"
        description="管理本地节点 + 远程 agent 节点;远程节点用 install.sh 一键部署"
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void refetch()} disabled={isLoading}>
              <RefreshCw size={14} className={'mr-2 ' + (isLoading ? 'animate-spin' : '')} />
              刷新
            </Button>
            <Button onClick={() => setAddOpen(true)}>
              <Plus size={14} className="mr-2" />
              添加节点
            </Button>
          </div>
        }
      />

      {isError && (
        <div className="rounded-md border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
          加载节点失败:{error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {isLoading && nodes.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={14} className="animate-spin" />
          加载中…
        </div>
      )}

      {!isLoading && nodes.length === 0 && (
        <EmptyState
          icon={Server}
          title="尚未注册任何远程节点"
          description="本地节点(local)默认存在,主面板自身可跑无浏览器依赖的脚本(如 coklw/ptfans)。需要 selenium / Chrome 的脚本(如 jmcomic)请添加远程节点。"
          action={
            <Button onClick={() => setAddOpen(true)}>
              <Plus size={14} className="mr-2" />
              添加节点
            </Button>
          }
        />
      )}

      {nodes.length > 0 && (
        <div className="grid gap-3">
          {nodes.map((node) => (
            <NodeCard key={node.id} node={node} />
          ))}
        </div>
      )}

      <AddNodeDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onCreated={(token, slug) => setNewToken({ token, slug })}
      />

      {newToken && (
        <TokenDisplayDialog
          open={!!newToken}
          onOpenChange={(v) => !v && setNewToken(null)}
          token={newToken.token}
          nodeSlug={newToken.slug}
          mode="fresh"
        />
      )}
    </div>
  );
}

export default NodeList;
