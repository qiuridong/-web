# 脚本货架 · 部署到生产 VPS 执行清单（154.9.238.144 / hub.aijiaxia.cc）

> 路径 B（与签到管家同机，复用 host nginx）。**整合阶段执行，每步与用户确认。**
> SSH：`ssh -i <密钥> root@154.9.238.144`（密钥见 `进度/README.md`「生产部署目标」段；
> ⚠️ Windows OpenSSH key 权限坑：拷到本地 NTFS + icacls 收紧再用，用完删）。

## 前置（已就绪 ✅）
- DNS A 记录 `hub.aijiaxia.cc → 154.9.238.144`（用户已添加）
- 货架前端 dist 本地已 build（`脚本货架/frontend/dist`，无 circular chunk）
- 货架 `docker-compose.yml`（backend 绑 `127.0.0.1:8100`）+ `deploy/nginx-hub.conf`

## 步骤

### 1. 打包货架 + dist，scp 到 VPS
```bash
# 本地（脚本货架/）：tar 后端源码 + 前端 dist + compose（排除 node_modules/.venv/data）
tar czf hub.tar.gz --exclude='**/node_modules' --exclude='**/.venv' --exclude='backend/data' \
    backend frontend/dist docker-compose.yml deploy/nginx-hub.conf
scp hub.tar.gz root@154.9.238.144:/opt/
# VPS：
mkdir -p /opt/signin-hub && tar xzf /opt/hub.tar.gz -C /opt/signin-hub
cp -r /opt/signin-hub/frontend/dist /opt/signin-hub/frontend_dist
```

### 2. 写 .env（CORS 放行管家）
```bash
# VPS /opt/signin-hub/.env
cat > /opt/signin-hub/.env <<'EOF'
ENVIRONMENT=production
COOKIE_SECURE=true
CORS_ORIGINS=https://jb.aijiaxia.cc
TZ=Asia/Shanghai
EOF
```

### 3. 起货架后端容器（8100）
```bash
cd /opt/signin-hub
mkdir -p backend/data backend/logs && chown -R 1000:1000 backend/data backend/logs
docker compose up -d --build
curl -fsS http://127.0.0.1:8100/health      # → {"status":"ok"...}
# lifespan 已自动建表 + 导入 3 种子
```

### 4. 建管理员
```bash
docker compose exec -T backend python seed_admin.py --username admin --password '<强随机密码>'
```

### 5. host nginx vhost（不影响主站 jb.aijiaxia.cc）
```bash
cp /opt/signin-hub/deploy/nginx-hub.conf /etc/nginx/sites-available/hub.aijiaxia.cc
ln -sf /etc/nginx/sites-available/hub.aijiaxia.cc /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 6. certbot 签证书（自动补 443 + 跳转）
```bash
certbot --nginx -d hub.aijiaxia.cc --non-interactive --agree-tos -m <邮箱>
```

### 7. smoke
```bash
curl -I https://hub.aijiaxia.cc/health          # 200
curl -s https://hub.aijiaxia.cc/api/scripts | head -c 200   # 3 脚本 JSON
# 浏览器开 https://hub.aijiaxia.cc 看画廊
# CORS：管家市场页（jb.aijiaxia.cc）能 fetch 到货架列表
```

## 回滚
```bash
rm -f /etc/nginx/sites-enabled/hub.aijiaxia.cc && systemctl reload nginx
cd /opt/signin-hub && docker compose down
```

## 后续迁移（换机）
旧机 `bash migrate-hub.sh export` → scp tar 到新机 →
`sudo bash install-hub.sh --access hub.example.com --email <邮箱> --restore hub-backup-xxx.tar.gz`
（新机走自包含 docker Caddy 路径，无需 host nginx）。
