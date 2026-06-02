#!/usr/bin/env bash
# =====================================================================
# 脚本货架 · 主站(154) → 备份兜底站(38/hub2) 每日数据同步
# 运行位置：38.49.208.71(pull 模型,所有逻辑在备份机,主站只被只读拉取)。
# cron 示例：  0 4 * * * /opt/sync-hub2.sh >> /var/log/hub2-sync.log 2>&1
#
# 机制：
#   1. SSH 到 154,在 hub 容器内用 sqlite3 .backup 做一致快照(WAL 安全)+ tar(db+scripts)
#   2. scp 拉到 38
#   3. 原子替换本地 backend/data(旧库留 .prev 可回滚)+ 清 -wal/-shm
#   4. docker compose restart backend(读新库)+ health 校验
#
# 依赖：38 上 /root/.ssh/hub2-sync(私钥,其 pub 已加到 154 authorized_keys,带 from= 限制)。
# =====================================================================
set -euo pipefail

# cron 环境 PATH 精简,显式补全以确保 docker/ssh/scp/tar/curl 可寻
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

MAIN_HOST="${MAIN_HOST:-154.9.238.144}"
MAIN_USER="${MAIN_USER:-root}"
SSH_KEY="${SSH_KEY:-/root/.ssh/hub2-sync}"
# 主站 hub 部署目录(154)——若主站迁移需同步改这里(也改下方 heredoc 内硬编码)
MAIN_DIR="/opt/signin-hub"

HUB="$(dirname "$(find /opt/sign-hub-src -maxdepth 2 -name install-hub.sh 2>/dev/null | head -1)")"
[ -n "$HUB" ] && [ -f "$HUB/docker-compose.yml" ] || { echo "本地货架目录未找到"; exit 1; }
DATA="$HUB/backend/data"
SSH="ssh -i $SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"

echo "[$(date '+%F %T')] hub2 sync start  <-  $MAIN_USER@$MAIN_HOST:$MAIN_DIR"

# ---- 1) 在 154 做一致快照(sqlite .backup,WAL 安全)+ 打包 db+scripts ----
# ⚠️ docker compose exec -T 必须 `< /dev/null`:否则它会把经 stdin(bash -s heredoc)喂入的
#    脚本剩余行当成容器 stdin 吃掉,导致 tar/echo 不执行、快照静默失败(踩过这个坑)。
$SSH "$MAIN_USER@$MAIN_HOST" bash -s <<'REMOTE'
set -e
cd /opt/signin-hub
docker compose exec -T backend python -c "import sqlite3; s=sqlite3.connect('/app/data/hub.sqlite3'); d=sqlite3.connect('/app/data/hub-sync.sqlite3'); s.backup(d); d.close(); s.close()" < /dev/null
tar czf /tmp/hub2-sync.tar.gz -C /opt/signin-hub/backend/data hub-sync.sqlite3 scripts
rm -f /opt/signin-hub/backend/data/hub-sync.sqlite3
echo REMOTE_SNAPSHOT_OK
REMOTE

# ---- 2) 拉到 38 ----
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$MAIN_USER@$MAIN_HOST:/tmp/hub2-sync.tar.gz" /tmp/hub2-sync.tar.gz

# ---- 3) 解包 staging + 校验 ----
STAGE="$(mktemp -d)"
tar xzf /tmp/hub2-sync.tar.gz -C "$STAGE"
[ -f "$STAGE/hub-sync.sqlite3" ] && [ -d "$STAGE/scripts" ] || { echo "BAD SNAPSHOT(缺 db 或 scripts)"; rm -rf "$STAGE"; exit 1; }

# ---- 4) 原子替换 data(旧库留 .prev) ----
mkdir -p "$DATA"
rm -rf "$DATA.prev"
cp -a "$DATA" "$DATA.prev" 2>/dev/null || true
mv "$STAGE/hub-sync.sqlite3" "$DATA/hub.sqlite3"
rm -f "$DATA/hub.sqlite3-wal" "$DATA/hub.sqlite3-shm"
rm -rf "$DATA/scripts"
mv "$STAGE/scripts" "$DATA/scripts"
chown -R 1000:1000 "$DATA"
rm -rf "$STAGE" /tmp/hub2-sync.tar.gz

# ---- 5) 重启后端读新库 + health ----
cd "$HUB"
docker compose restart backend >/dev/null 2>&1
ok=0
for _ in $(seq 1 20); do curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1 && { ok=1; break; }; sleep 2; done
N="$(curl -s http://127.0.0.1:8100/api/scripts | grep -o '"slug"' | wc -l)"
[ "$ok" = "1" ] && echo "[$(date '+%F %T')] hub2 sync done; backend healthy; scripts=$N" \
                 || { echo "[$(date '+%F %T')] sync 后端未就绪(查 docker compose logs)"; exit 1; }
