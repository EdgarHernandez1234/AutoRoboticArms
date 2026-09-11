# =====================================================================
# STAGE 1: Builder Layer (C-Extension & Wheelhouse Compiler)
# =====================================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

# 1. Install compiler toolchains for native C/Rust extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade core build tools to parse modern platform tags
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 3. Copy dependency manifest and compile binary wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --prefer-binary --wheel-dir=/tmp/wheels -r requirements.txt


# =====================================================================
# STAGE 2: Hardened Runtime Layer (Air-Gapped & Drop Privileges)
# =====================================================================
FROM python:3.11-slim AS runtime

# Explicit Python module pathing to resolve 'src' imports
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Create non-root user and group (UID/GID 1000) with no shell access
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /sbin/nologin -m appuser

WORKDIR /app

# 2. Copy pre-compiled wheels & manifest from Stage 1
COPY --from=builder /tmp/wheels /tmp/wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# 3. Air-Gapped Installation: Install offline and purge wheels immediately
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt && \
    rm -rf /tmp/wheels

# 4. Copy application code with non-root user ownership
COPY --chown=appuser:appgroup . /app

# 5. Set POSIX permission boundaries:
#    - Immutable Code Layer: Read & Execute (550) on /app
#    - Write-Ahead Logging Layer: Read & Write (770) exclusively on /app/storage
RUN chown -R appuser:appgroup /app && \
    chmod 755 /app && \
    chmod -R 555 /app && \
    mkdir -p /app/storage && \
    chown -R appuser:appgroup /app/storage && \
    chmod -R 770 /app/storage

# 6. Built-in urllib diagnostic health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/health')" || exit 1

# 7. Drop root privileges permanently to appuser (UID 10001)
USER appuser:appgroup

EXPOSE 8050

# 8. Launch Uvicorn ASGI Server anchored explicitly to /app
CMD ["uvicorn", "src.control_plane:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8050"]