#!/usr/bin/env bash
# =====================================================================
# 脚本货架 · 备份兜底站 hub2 部署（host nginx vhost 路径,仿 154 主站）
# 适用：目标机已有 host nginx 占用 80/443(如 seedbox)，不能用自包含 Caddy。
#
# 前置：在目标机已 git clone repo 到 $SRC(默认 /opt/sign-hub-src,-b feat/script-hub)。
# 本脚本：构建前端 dist + 起后端容器(127.0.0.1:8100) + 等 health。
# nginx vhost(nginx-hub2.conf) / certbot / 每日同步(sync-to-hub2.sh) 另行执行。
#
# 用法：bash 部署hub2备份站.sh [SRC目录]
# =====================================================================
set -euo pipefail

SRC="${1:-/opt/sign-hub-src}"
# 用 install-hub.sh 定位货架子目录(避免硬编码中文路径)
HUB="$(dirname "$(find "$SRC" -maxdepth 2 -name install-hub.sh 2>/dev/null | head -1)")"
[ -n "$HUB" ] && [ -f "$HUB/docker-compose.yml" ] || { echo "未找到货架目录(先 git clone 到 $SRC)"; exit 1; }
cd "$HUB"
echo "HUB=$HUB"

# .env(幂等)。后端 CORS 已硬编码 allow_origins=["*"](公开读),故 CORS_ORIGINS 留空即可。
# ⚠️ COMPOSE_PROJECT_NAME 必填：cwd 是中文目录(脚本货架),docker compose 无法从中文目录名
#    推导项目名(报 "project name must not be empty"),必须显式给一个 ASCII 项目名。
if [ ! -f .env ]; then
  cat > .env <<EOF
ENVIRONMENT=production
COOKIE_SECURE=true
CORS_ORIGINS=
TZ=Asia/Shanghai
COMPOSE_PROJECT_NAME=signin-hub2
EOF
fi
grep -q COMPOSE_PROJECT_NAME .env || echo COMPOSE_PROJECT_NAME=signin-hub2 >> .env

mkdir -p backend/data backend/logs
chown -R 1000:1000 backend/data backend/logs 2>/dev/null || true

echo "=== [1/3] 构建前端 dist(docker node:20-alpine,免装 node) ==="
docker run --rm -v "$HUB/frontend":/app -w /app node:20-alpine \
  sh -c "corepack enable && pnpm install && pnpm build"
rm -rf ./frontend_dist 2>/dev/null || true
cp -r frontend/dist ./frontend_dist
echo "dist 就绪：$(ls ./frontend_dist | wc -l) 项"

echo "=== [2/3] 构建 + 起后端容器(127.0.0.1:8100) ==="
docker compose up -d --build

echo "=== [3/3] 等待 health ==="
ok=0
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
curl -s http://127.0.0.1:8100/health || true
echo ""
[ "$ok" = "1" ] && echo "BUILD_ALL_DONE" || { echo "HEALTH_TIMEOUT(查 docker compose logs backend)"; exit 1; }
