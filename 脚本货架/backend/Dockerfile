# =========================================
# 脚本货架 · 后端 Dockerfile（多阶段 uv，仿主项目）
# =========================================
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv
WORKDIR /build

COPY pyproject.toml ./
COPY uv.lock* ./
COPY README.md ./

RUN if [ ! -f uv.lock ]; then uv lock; fi && \
    uv export --no-dev --no-header --format requirements-txt > /tmp/requirements.txt && \
    uv pip install --system --no-cache --target /deps -r /tmp/requirements.txt

# ===== runtime =====
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/deps \
    PATH=/deps/bin:$PATH \
    TZ=Asia/Shanghai \
    PYTHONIOENCODING=utf-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini ca-certificates tzdata && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 app && \
    useradd -u 1000 -g 1000 -m -s /bin/bash app && \
    mkdir -p /app/data /app/logs && \
    chown -R app:app /app

WORKDIR /app
COPY --from=builder /deps /deps
COPY --chown=app:app . .
USER app

EXPOSE 8000
ENTRYPOINT ["tini", "--"]
# 单 worker：lifespan 建表 + 种子导入幂等，单进程最稳（货架无调度器，但 SQLite 写 + 首启种子）
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
