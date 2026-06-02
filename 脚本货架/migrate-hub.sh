#!/usr/bin/env bash
# =====================================================================
# 脚本货架 · 一键迁移（导出 / 导入）
# 货架数据极简（无加密密钥）：打包 backend/data（hub.sqlite3 + scripts/）+ .env。
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

cmd="${1:-}"
case "$cmd" in
  export)
    ts="$(date +%Y%m%d-%H%M%S)"
    out="$HERE/hub-backup-$ts.tar.gz"
    files=("backend/data")
    [ -f ".env" ] && files+=(".env")
    [ -d "backend/data" ] || { echo "错误：backend/data 不存在，没有可导出的数据"; exit 1; }
    tar -czf "$out" -C "$HERE" "${files[@]}"
    echo "已导出: $out"
    echo "包含:   ${files[*]}"
    echo "大小:   $(du -h "$out" | cut -f1)"
    ;;
  import)
    tarball="${2:-}"
    [ -n "$tarball" ] || { echo "用法: $0 import <tarball>"; exit 1; }
    [ -f "$tarball" ] || { echo "错误：文件不存在: $tarball"; exit 1; }
    tar -xzf "$tarball" -C "$HERE"
    chown -R 1000:1000 backend/data 2>/dev/null || true
    echo "已还原到 backend/data"
    echo "如服务正在运行，请执行: docker compose restart backend"
    echo "（或先 install-hub.sh 部署环境，它会自动起服务）"
    ;;
  *)
    echo "脚本货架迁移工具"
    echo "用法:"
    echo "  $0 export              导出当前数据为 hub-backup-<时间戳>.tar.gz"
    echo "  $0 import <tarball>    从迁移包还原数据"
    exit 1
    ;;
esac
