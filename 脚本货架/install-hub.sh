#!/usr/bin/env bash
# =====================================================================
# 脚本货架 · 一键自部署（仿主项目 install-panel.sh）
# 用于全新干净机器：docker Caddy 自动 HTTPS + serve 前端 dist + 反代 /api。
# 货架无 alembic（lifespan 自动 create_all + 种子导入），故无迁移步。
# =====================================================================
set -euo pipefail

ACCESS=""           # 域名 或 公网 IP
EMAIL=""
HTTP_ONLY=0
RESTORE=""
ADMIN_USER="admin"

usage() {
  cat <<EOF
用法: sudo bash install-hub.sh --access <域名或公网IP> [选项]

  --access <值>     必填。域名（如 hub.example.com）或公网 IP（自动 <ip>.sslip.io 证书）
  --email <邮箱>    Let's Encrypt 注册邮箱（HTTPS 推荐填）
  --http            纯 HTTP 兜底（无证书，COOKIE_SECURE=false，仅内网/调试）
  --restore <包>    部署同时还原迁移包（migrate-hub.sh export 产物）
  --admin-user <名> 管理员用户名（默认 admin）
  -h, --help        显示帮助

示例:
  sudo bash install-hub.sh --access hub.example.com --email you@example.com
  sudo bash install-hub.sh --access 1.2.3.4 --email you@example.com
  sudo bash install-hub.sh --access 1.2.3.4 --http
  sudo bash install-hub.sh --access hub.example.com --email you@e.com --restore hub-backup-xxx.tar.gz
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --access) ACCESS="${2:-}"; shift 2;;
    --email) EMAIL="${2:-}"; shift 2;;
    --http) HTTP_ONLY=1; shift;;
    --restore) RESTORE="${2:-}"; shift 2;;
    --admin-user) ADMIN_USER="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "未知参数: $1"; usage; exit 1;;
  esac
done

[ -n "$ACCESS" ] || { echo "错误：必须提供 --access <域名或公网IP>"; usage; exit 1; }

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
COMPOSE="docker compose -f docker-compose.install.yml"

echo "[1/7] 检查 Docker"
command -v docker >/dev/null 2>&1 || { echo "请先安装 docker"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "需要 docker compose v2 插件"; exit 1; }

echo "[2/7] 计算访问地址 + 写 .env"
is_ip() { echo "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; }
if [ "$HTTP_ONLY" = "1" ]; then
  DOMAIN="http://$ACCESS"; COOKIE_SECURE="false"; SHOW="http://$ACCESS"
elif is_ip "$ACCESS"; then
  DOMAIN="${ACCESS}.sslip.io"; COOKIE_SECURE="true"; SHOW="https://${ACCESS}.sslip.io"
else
  DOMAIN="$ACCESS"; COOKIE_SECURE="true"; SHOW="https://$ACCESS"
fi
cat > .env <<EOF
TZ=Asia/Shanghai
DOMAIN=$DOMAIN
ACME_EMAIL=$EMAIL
COOKIE_SECURE=$COOKIE_SECURE
CORS_ORIGINS=
EOF
echo "  DOMAIN=$DOMAIN  COOKIE_SECURE=$COOKIE_SECURE"

echo "[3/7] 准备数据目录"
mkdir -p backend/data backend/logs
chown -R 1000:1000 backend/data backend/logs 2>/dev/null || true

echo "[4/7] 还原迁移包（如指定）"
if [ -n "$RESTORE" ]; then
  [ -f "$RESTORE" ] || { echo "迁移包不存在: $RESTORE"; exit 1; }
  tar -xzf "$RESTORE" -C "$HERE"
  chown -R 1000:1000 backend/data 2>/dev/null || true
  echo "  已还原 $RESTORE"
else
  echo "  跳过（未指定 --restore）"
fi

echo "[5/7] 构建前端 dist（docker 内，免装 node）"
docker run --rm -v "$HERE/frontend":/app -w /app node:20-alpine \
  sh -c "corepack enable && pnpm install && pnpm build"
rm -rf frontend_dist && cp -r frontend/dist frontend_dist
echo "  dist 就绪"

echo "[6/7] 构建后端镜像 + 启动 caddy + backend"
$COMPOSE build backend
$COMPOSE up -d
echo "  等待后端就绪..."
READY=0
for _ in $(seq 1 30); do
  if $COMPOSE exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=3)" >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 2
done
[ "$READY" = "1" ] && echo "  后端 healthy" || echo "  ⚠️ 后端未在 60s 内就绪，请查 $COMPOSE logs backend"

echo "[7/7] 创建管理员（随机密码，幂等）"
PASS="$(openssl rand -base64 18 2>/dev/null | tr -dc 'A-Za-z0-9' | cut -c1-16 || true)"
[ -n "$PASS" ] || PASS="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | cut -c1-16)"
OUT="$($COMPOSE exec -T backend python seed_admin.py --username "$ADMIN_USER" --password "$PASS" 2>&1 || true)"
echo "$OUT" | grep -q "SEED_OK" && CREATED=1 || CREATED=0

echo ""
echo "============================================================"
echo "  脚本货架部署完成"
echo "------------------------------------------------------------"
echo "  访问:    $SHOW"
if [ "$CREATED" = "1" ]; then
  echo "  管理员:  $ADMIN_USER"
  echo "  密码:    $PASS"
  echo "  ⚠️ 请立即登录并妥善保存密码"
else
  echo "  管理员:  已存在（用现有账号登录）"
fi
echo "  种子脚本: 首次启动已自动导入 seed/scripts/"
echo "============================================================"
