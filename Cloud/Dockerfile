# =====================================================================
# STAGE 1: Builder Layer (C-Extension & Wheelhouse Compiler)
# =====================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

WORKDIR /app

# 1. Install compiler toolchains for native C/Rust extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 2. Upgrade core build tools to parse modern platform tags
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip wheel --no-cache-dir --prefer-binary --wheel-dir /app/wheels -r requirements.txt

# =====================================================================
# STAGE 2: Hardened Runtime Layer (Air-Gapped & Drop Privileges)
# =====================================================================
FROM python:3.12-slim AS runtime

# Explicit Python module pathing to resolve 'src' imports
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=850

WORKDIR /app

# 1. Provision unprivileged system identity (appuser:appgroup, UID/GID 1000)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /sbin/nologin appuser

# 2. Pre-provision zero-trust AWS credential directory owned by UID 1000
RUN mkdir -p /home/appuser/.aws && \
    chown -R appuser:appgroup /home/appuser

# 3. Pre-provision dedicated SQLite WAL persistence directory with 770 permissions
RUN mkdir -p /app/storage && \
    chown -R appuser:appgroup /app/storage && \
    chmod 770 /app/storage

# 4. Air-gapped dependency installation from Stage 1 wheels
COPY --from=builder /app/wheels /tmp/wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels

# 5. Copy application source tree and enforce immutable read/execute bits
COPY src/ /app/src/
RUN chown -R appuser:appgroup /app/src && \
    chmod -R 555 /app/src

# 6. Expose the ASGI control plane port
EXPOSE 8050


# 7. Built-in urllib diagnostic health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/health')" || exit 1

# 8. Drop root privileges permanently to appuser (UID 10001)
USER appuser:appgroup

EXPOSE 8050

# 8. Launch Uvicorn ASGI Server anchored explicitly to /app
CMD ["uvicorn", "src.control_plane:app", "--host", "0.0.0.0", "--port", "8050"]
