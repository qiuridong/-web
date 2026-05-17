# =========================================
# 前端构建镜像 — 仅 builder 阶段
# =========================================
# 用法:`docker build -t signin-panel-frontend-builder .`
# 产物:/app/dist (由 docker-compose 把 host ./frontend/dist 挂给 caddy serve,
#       一般 CI/local 直接 `pnpm build` 即可,本 Dockerfile 主要给 docker-only 部署用)
# =========================================

FROM node:20-alpine AS builder

WORKDIR /app

# 启用 corepack 管理的 pnpm
RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

# 利用层缓存
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

# 拷贝其余源代码
COPY . .

# 类型检查 + 构建
ENV NODE_ENV=production
RUN pnpm build

# 暴露 dist 作为镜像内容(下游 compose 用 multi-stage copy 或挂 volume)
# 末段省略 runtime stage,因为 dist 由 caddy serve(见 docker-compose.yml caddy.volumes)
