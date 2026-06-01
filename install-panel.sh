#!/usr/bin/env bash
# =========================================================================
# 签到管家 · 一键自部署安装脚本(面板本体,非 agent)
# =========================================================================
# 在干净的 Ubuntu/Debian VPS 上一条命令起全套(Docker + Caddy 自动 HTTPS + 后端):
#
#   # 有域名(自动 Let's Encrypt HTTPS):
#   sudo bash install-panel.sh --access your.domain.com --email you@example.com
#
#   # 无域名、只有公网 IP(自动用 <ip>.sslip.io 出真 HTTPS,免买域名):
#   sudo bash install-panel.sh --access 1.2.3.4 --email you@example.com
#
#   # 纯 HTTP(仅内网/调试,不签证书;会自动关 Secure cookie):
#   sudo bash install-panel.sh --access 1.2.3.4 --http
#
# 完成后打印:访问地址 + 管理员账号/密码(随机生成,提示登录后改)。
# 不附带任何已有签到脚本 —— 装好是空面板,自己在「脚本」页上传。
# =========================================================================
set -euo pipefail

REPO_URL="https://github.com/qiuridong/-web"
ACCESS=""; ACME_EMAIL=""; ADMIN_USER="admin"; ADMIN_PASS=""; FORCE_HTTP=0; TZ_VAL="Asia/Shanghai"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --access)     ACCESS="$2"; shift 2 ;;
    --email)      ACME_EMAIL="$2"; shift 2 ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --admin-pass) ADMIN_PASS="$2"; shift 2 ;;
    --http)       FORCE_HTTP=1; shift ;;
    --timezone)   TZ_VAL="$2"; shift 2 ;;
    -h|--help)
      cat <<HELP
签到管家 一键自部署
  --access DOMAIN|IP   必填。域名(自动 HTTPS)或公网 IP(默认 <ip>.sslip.io 免域名 HTTPS)
  --email  EMAIL       证书申请邮箱(HTTPS 时建议填)
  --admin-user NAME    管理员用户名(默认 admin)
  --admin-pass PASS    管理员密码(默认随机生成并在结尾打印)
  --http               纯 HTTP 不签证书(仅内网/调试;自动设 COOKIE_SECURE=false)
  --timezone TZ        时区(默认 Asia/Shanghai)
HELP
      exit 0 ;;
    *) echo "❌ 未知参数: $1(--help 看用法)"; exit 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "❌ 需要 root 运行(装 docker + 绑 80/443)"; exit 1; }
[[ -n "$ACCESS" ]] || { echo "❌ 缺 --access <域名|公网IP>,见 --help"; exit 1; }

echo "============================================================"
echo "签到管家 一键自部署 · $(date '+%F %T')"
echo "============================================================"

# ---- 1. Docker ----
if ! command -v docker >/dev/null 2>&1; then
  echo "[1/8] 安装 Docker..."
  curl -fsSL https://get.docker.com | sh
else
  echo "[1/8] Docker 已装:$(docker --version)"
fi
docker compose version >/dev/null 2>&1 || { echo "❌ 需要 docker compose v2(随新版 docker 一起装)"; exit 1; }

# ---- 2. 取代码 ----
if [[ ! -f docker-compose.install.yml ]]; then
  echo "[2/8] 拉取代码 $REPO_URL ..."
  command -v git >/dev/null 2>&1 || { apt-get update -y && apt-get install -y git; }
  git clone --depth 1 "$REPO_URL" signin-panel
  cd signin-panel
else
  echo "[2/8] 已在仓库目录,跳过 clone"
fi

# ---- 3. 访问方式 → DOMAIN / COOKIE_SECURE ----
if [[ "$ACCESS" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then IS_IP=1; else IS_IP=0; fi
if [[ $FORCE_HTTP -eq 1 ]]; then
  DOMAIN_VAL="http://$ACCESS"; COOKIE_SECURE_VAL="false"; SCHEME="http"
  echo "  纯 HTTP 模式(无证书,Secure cookie 关)"
elif [[ $IS_IP -eq 1 ]]; then
  DOMAIN_VAL="${ACCESS}.sslip.io"; COOKIE_SECURE_VAL="true"; SCHEME="https"
  echo "  无域名 → 魔法 DNS ${DOMAIN_VAL}(解析到 ${ACCESS})自动签 HTTPS"
else
  DOMAIN_VAL="$ACCESS"; COOKIE_SECURE_VAL="true"; SCHEME="https"
fi
ACCESS_URL="${SCHEME}://${DOMAIN_VAL#http://}"

# ---- 4. .env ----
echo "[3/8] 写 .env(DOMAIN=$DOMAIN_VAL, COOKIE_SECURE=$COOKIE_SECURE_VAL)..."
cat > .env <<ENVEOF
TZ=$TZ_VAL
ENVIRONMENT=production
COOKIE_SECURE=$COOKIE_SECURE_VAL
DOMAIN=$DOMAIN_VAL
ACME_EMAIL=$ACME_EMAIL
DATABASE_URL=sqlite:////app/data/db.sqlite3
SCHEDULER_DB_URL=sqlite:////app/data/scheduler.db
ENCRYPTION_KEY_PATH=/app/data/encryption.key
LOG_LEVEL=INFO
WORKERS=1
SCRIPTS_DIR=/app/scripts
ENVEOF

# ---- 5. 目录(容器内 app=1000:1000 要可写)+ 清空 scripts ----
echo "[4/8] 准备 data/scripts/logs(清空 scripts,空面板起步)..."
mkdir -p data scripts logs
rm -rf scripts/* 2>/dev/null || true
touch scripts/.gitkeep
chown -R 1000:1000 data scripts logs

# ---- 6. 前端 dist(docker 内 build,免在本机装 node)----
echo "[5/8] 构建前端 dist(docker)..."
docker build -t signin-panel-frontend-builder ./frontend
cid=$(docker create signin-panel-frontend-builder)
rm -rf frontend/dist
docker cp "$cid:/app/dist" frontend/dist
docker rm -f "$cid" >/dev/null
echo "  ✓ frontend/dist 就绪"

DC="docker compose -f docker-compose.install.yml"

# ---- 7. 后端镜像 + 迁移 + 起服务 ----
echo "[6/8] 构建后端镜像..."
$DC build backend
echo "[7/8] 数据库迁移 + 启动 caddy + backend..."
$DC run --rm backend alembic upgrade head
$DC up -d

echo -n "  等待后端就绪"
for _ in $(seq 1 30); do
  if $DC exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=3)" >/dev/null 2>&1; then
    echo " ✓"; break
  fi
  echo -n "."; sleep 2
done

# ---- 8. 管理员 + 打印账密 ----
echo "[8/8] 创建管理员..."
if [[ -z "$ADMIN_PASS" ]]; then
  ADMIN_PASS=$(openssl rand -base64 15 2>/dev/null | tr -d '/+=' | cut -c1-16 || true)
  [[ -n "$ADMIN_PASS" ]] || ADMIN_PASS=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16)
fi
SEED_OUT=$($DC exec -T backend python seed_admin.py --username "$ADMIN_USER" --password "$ADMIN_PASS" 2>&1 || true)
echo "  $SEED_OUT"

echo
echo "============================================================"
echo "✅ 部署完成!"
echo "------------------------------------------------------------"
echo "  访问地址 : $ACCESS_URL"
if echo "$SEED_OUT" | grep -q '^SEED_OK'; then
  echo "  管理员   : $ADMIN_USER"
  echo "  密码     : $ADMIN_PASS"
  echo "  ⚠️ 登录后请立刻到「设置」修改密码!此密码仅此一次显示。"
elif echo "$SEED_OUT" | grep -q '^SEED_SKIP'; then
  echo "  管理员   : 已存在,用你原有账号登录"
else
  echo "  ⚠️ 管理员创建异常,可手动重试:"
  echo "    $DC exec backend python seed_admin.py --username admin --password '你的密码'"
fi
echo "------------------------------------------------------------"
echo "  常用命令(在本目录执行):"
echo "    $DC logs -f backend     # 后端日志"
echo "    $DC logs -f caddy       # 证书/反代日志"
echo "    $DC ps                  # 状态"
echo "    $DC restart backend     # 重启后端"
echo "  ⚠️ data/encryption.key 是主密钥,请立即异地备份(丢失 = 所有加密配置作废)"
[[ "$SCHEME" == "https" ]] && echo "  注:首访 Caddy 需几十秒签发证书;用域名请确保 DNS 已解析到本机公网 IP"
echo "============================================================"
