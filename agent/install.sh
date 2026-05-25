#!/usr/bin/env bash
# signin-agent 一键安装脚本
#
# 用法:
#   sudo bash install.sh --master https://jb.aijiaxia.cc --token sa_xxxxx --node-slug vps-jm
#
# 自动:
#   - 装 Python 依赖(httpx + PyYAML)
#   - 建目录 /opt/signin-agent + /etc/signin-agent + /var/log/signin-agent + /var/lib/signin-agent
#   - 复制 signin_agent.py + sandbox_runner.py 到 /opt/signin-agent/
#   - 写 /etc/signin-agent/config.yaml(chmod 600)
#   - 写 /etc/systemd/system/signin-agent.service
#   - systemctl enable --now signin-agent
#   - 验证 + 显示状态

set -euo pipefail

# ============================================================
# 默认
# ============================================================
INSTALL_DIR=/opt/signin-agent
CONFIG_DIR=/etc/signin-agent
LOG_DIR=/var/log/signin-agent
DATA_DIR=/var/lib/signin-agent/data
SCRIPTS_DIR=$INSTALL_DIR/scripts
PYTHON_BIN=/usr/bin/python3
SERVICE_NAME=signin-agent
TIMEZONE=Asia/Shanghai

# ============================================================
# 参数解析
# ============================================================
MASTER_URL=""
NODE_TOKEN=""
NODE_SLUG=""
SOURCE_DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --master) MASTER_URL="$2"; shift 2 ;;
    --token) NODE_TOKEN="$2"; shift 2 ;;
    --node-slug) NODE_SLUG="$2"; shift 2 ;;
    --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    --timezone) TIMEZONE="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    -h|--help)
      cat <<HELP
signin-agent 一键安装

用法:
  sudo bash install.sh --master URL --token TOKEN --node-slug SLUG [options]

必需参数:
  --master URL          主面板地址(如 https://jb.aijiaxia.cc)
  --token TOKEN         节点 token(由主面板创建节点时返回,sa_ 开头)
  --node-slug SLUG      节点标识符(只用于日志显示)

可选参数:
  --scripts-dir PATH    脚本目录(默认 $SCRIPTS_DIR)
  --python BIN          Python 解释器(默认 $PYTHON_BIN)
  --timezone TZ         时区(默认 $TIMEZONE)
  --install-dir DIR     安装目录(默认 $INSTALL_DIR)

完成后:
  - systemctl status signin-agent  # 看状态
  - journalctl -u signin-agent -f  # 看日志
HELP
      exit 0 ;;
    *)
      echo "❌ 未知参数: $1(--help 看用法)"
      exit 1 ;;
  esac
done

# ============================================================
# 校验
# ============================================================
if [[ -z "$MASTER_URL" || -z "$NODE_TOKEN" ]]; then
  echo "❌ 缺少 --master 或 --token,见 --help"
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "❌ 必须以 root 运行(systemd unit + /etc 写入)"
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "❌ Python 不存在: $PYTHON_BIN"
  exit 1
fi

echo "============================================================"
echo "signin-agent 安装 $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo "  master_url : $MASTER_URL"
echo "  node_slug  : ${NODE_SLUG:-(未填,仅日志用)}"
echo "  install_dir: $INSTALL_DIR"
echo "  scripts_dir: $SCRIPTS_DIR"
echo "  python_bin : $PYTHON_BIN ($($PYTHON_BIN --version))"
echo "  timezone   : $TIMEZONE"
echo

# ============================================================
# [1] Python 依赖
# ============================================================
echo "[1/7] 装 Python 依赖(httpx + PyYAML)..."
if $PYTHON_BIN -c "import httpx, yaml" 2>/dev/null; then
  echo "  ✓ 已装"
else
  $PYTHON_BIN -m pip install --break-system-packages --quiet httpx pyyaml 2>/dev/null \
    || $PYTHON_BIN -m pip install --quiet httpx pyyaml
  echo "  ✓ 完成"
fi

# ============================================================
# [2] 建目录
# ============================================================
echo "[2/7] 创建目录..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$DATA_DIR" "$SCRIPTS_DIR"
chmod 700 "$CONFIG_DIR"
echo "  ✓ $INSTALL_DIR / $CONFIG_DIR / $LOG_DIR / $DATA_DIR / $SCRIPTS_DIR"

# ============================================================
# [3] 部署主程序 + sandbox_runner
# ============================================================
echo "[3/7] 部署 signin_agent.py + sandbox_runner.py..."

if [[ -f "$SOURCE_DIR/signin_agent.py" ]]; then
  cp "$SOURCE_DIR/signin_agent.py" "$INSTALL_DIR/signin_agent.py"
  chmod 755 "$INSTALL_DIR/signin_agent.py"
  echo "  ✓ signin_agent.py → $INSTALL_DIR/"
else
  echo "  ❌ 源 signin_agent.py 不在 $SOURCE_DIR/"
  exit 1
fi

if [[ -f "$SOURCE_DIR/sandbox_runner.py" ]]; then
  cp "$SOURCE_DIR/sandbox_runner.py" "$INSTALL_DIR/sandbox_runner.py"
  chmod 755 "$INSTALL_DIR/sandbox_runner.py"
  echo "  ✓ sandbox_runner.py → $INSTALL_DIR/"
else
  echo "  ⚠️  sandbox_runner.py 不在 $SOURCE_DIR/"
  echo "    请手动从主面板拷贝:"
  echo "    scp <主面板 IP>:/opt/signin-panel/backend/sandbox_runner.py $INSTALL_DIR/"
  echo "    或手动 wget 一份(后续可补)"
fi

# ============================================================
# [4] 写 config.yaml
# ============================================================
echo "[4/7] 写 $CONFIG_DIR/config.yaml..."
cat > "$CONFIG_DIR/config.yaml" <<CFGEOF
# signin-agent 配置(install.sh 自动生成 $(date '+%Y-%m-%d %H:%M:%S'))
# 参考: $INSTALL_DIR/README.md
#
# 修改后需要 systemctl restart signin-agent

# 主面板地址
master_url: $MASTER_URL

# 节点 token(由主面板创建节点时一次性生成)
node_token: $NODE_TOKEN

# 脚本目录(放置 scripts/<slug>/main.py + manifest.yaml + ...)
scripts_dir: $SCRIPTS_DIR

# Python 解释器
python_bin: $PYTHON_BIN

# sandbox_runner.py 路径
sandbox_runner: $INSTALL_DIR/sandbox_runner.py

# 实例 data_dir 根(每个实例独立子目录 instance-<id>/)
data_dir: $DATA_DIR

# 时区(影响子进程 TZ 环境变量)
timezone: $TIMEZONE

# 日志级别(DEBUG / INFO / WARNING / ERROR)
log_level: INFO
CFGEOF
chmod 600 "$CONFIG_DIR/config.yaml"
echo "  ✓ chmod 600 $CONFIG_DIR/config.yaml"

# ============================================================
# [5] systemd unit
# ============================================================
echo "[5/7] 写 /etc/systemd/system/$SERVICE_NAME.service..."
cat > /etc/systemd/system/$SERVICE_NAME.service <<SVCEOF
[Unit]
Description=signin-agent — 签到管家远程节点 agent
Documentation=https://github.com/qiuridong/-web
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=$PYTHON_BIN $INSTALL_DIR/signin_agent.py --config $CONFIG_DIR/config.yaml
Environment=TZ=$TIMEZONE
Environment=PYTHONIOENCODING=utf-8
StandardOutput=append:$LOG_DIR/agent.log
StandardError=append:$LOG_DIR/agent.log
Restart=on-failure
RestartSec=10s
KillSignal=SIGTERM
TimeoutStopSec=60s

# 资源约束(留够 Chrome 用)
# Chrome selenium 跑时一个实例可能起 50-100 个进程(renderer + utility + gpu + network 等)
# + Xvfb + chromedriver + signin_agent 主线程 + heartbeat thread + sandbox_runner 子进程
# 实测 128 会被 cgroup `fork rejected by pids controller` 拒;改 4096 留充裕空间
# 内存:Chrome 峰值 1.5G(README 注明),给 2G 留余量
MemoryMax=2G
TasksMax=4096

[Install]
WantedBy=multi-user.target
SVCEOF
echo "  ✓ $SERVICE_NAME.service 写入"

# ============================================================
# [6] 启动 systemd
# ============================================================
echo "[6/7] daemon-reload + enable --now..."
systemctl daemon-reload
systemctl enable --now $SERVICE_NAME

# ============================================================
# [7] 验证
# ============================================================
sleep 3
echo "[7/7] 验证..."
echo
echo "--- systemctl status $SERVICE_NAME ---"
systemctl status $SERVICE_NAME --no-pager -l | head -20
echo
echo "--- 最近日志(20 行)---"
tail -20 $LOG_DIR/agent.log 2>/dev/null || echo "(日志还没生成)"
echo
echo "============================================================"
echo "✅ 安装完成"
echo
echo "常用命令:"
echo "  systemctl status $SERVICE_NAME       # 看状态"
echo "  systemctl restart $SERVICE_NAME      # 重启"
echo "  systemctl stop $SERVICE_NAME         # 停止"
echo "  systemctl disable $SERVICE_NAME      # 禁用开机启动"
echo "  journalctl -u $SERVICE_NAME -f       # 跟踪日志"
echo "  tail -f $LOG_DIR/agent.log           # 跟踪日志(文件)"
echo
echo "配置文件: $CONFIG_DIR/config.yaml(改完 restart 生效)"
echo "脚本目录: $SCRIPTS_DIR(放 scripts/<slug>/main.py 等)"
echo "============================================================"
