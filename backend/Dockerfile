# =========================================
# 签到脚本聚合管理面板 · 后端 Dockerfile
# =========================================
# 多阶段构建:builder 用 uv 解析依赖装到 /deps,runtime 仅含运行所需
# 镜像目标体积:~250-300MB
# =========================================

# ===== Stage 1: builder =====
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 装 uv(比 pip 快 10-100 倍)
RUN pip install --no-cache-dir uv

WORKDIR /build

# 仅复制依赖描述文件,最大化利用 docker 缓存
COPY pyproject.toml ./
# uv.lock 若已生成则一同复制(首次 build 时可不存在)
COPY uv.lock* ./
# pyproject 的 readme 字段引用 README.md,hatchling 解析时需要它存在
COPY README.md ./

# 把依赖装到 /deps(不要装到默认 site-packages,便于 runtime 阶段干净复制)
# /bin/sh 不支持 <(...) bash 进程替换,改两步:先生成 lock + 导出 requirements,再 install
RUN if [ ! -f uv.lock ]; then uv lock; fi && \
    uv export --no-dev --no-header --format requirements-txt > /tmp/requirements.txt && \
    uv pip install --system --no-cache --target /deps -r /tmp/requirements.txt

# ===== Stage 2: runtime =====
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/deps \
    PATH=/deps/bin:$PATH \
    TZ=Asia/Shanghai \
    PYTHONIOENCODING=utf-8

# 运行时必需:tini(PID1 信号处理)+ ca-certificates(HTTPS)+ tzdata(时区)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        tzdata && \
    rm -rf /var/lib/apt/lists/*

# 固定非 root 用户(与 host 文件属主对齐,典型 1000:1000)
RUN groupadd -g 1000 app && \
    useradd -u 1000 -g 1000 -m -s /bin/bash app && \
    mkdir -p /app/data /app/scripts /app/logs && \
    chown -R app:app /app

WORKDIR /app

# 复制依赖
COPY --from=builder /deps /deps

# 复制应用源码
COPY --chown=app:app . .

# 切换非 root
USER app

EXPOSE 8000

# tini 当 PID1
ENTRYPOINT ["tini", "--"]

# uvicorn 必须 --workers 1(APScheduler 同进程模式禁止多 worker)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
