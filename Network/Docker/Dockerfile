# =====================================================================
# STAGE 1: Build & Dependency Resolution Environment
# =====================================================================
FROM python:3.11-slim AS builder

# Force Python output to stream directly to stdout/stderr without buffering
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Install compilation prerequisites safely via package manager tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolate dependency caching parameters cleanly
COPY requirements.txt .

# Compile Python dependencies directly into a localized user folder space 
# to bypass systemic root installation vectors completely
RUN pip install --no-cache-dir --user -r requirements.txt


# =====================================================================
# STAGE 2: Secure Production Microservice Target Runtime
# =====================================================================
FROM python:3.11-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH

WORKDIR /app

# Provision an unprivileged local system user profile to execute the daemon logic
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Extract completed binary assets across isolation boundaries from the builder phase
COPY --from=builder /root/.local /home/appuser/.local
COPY --from=builder /build /app

# Transfer application workspace code structures down into the file engine environment
COPY ./src /app/src

# Rigidly secure ownership metrics before stepping down privilege constraints
RUN chown -R appuser:appgroup /app

# Switch execution rings away from root to the non-privileged user profile
USER appuser

# Document the intended application network gateway target configuration space
EXPOSE 8080

# Assert the definitive application initialization runtime loop entry barrier
CMD ["python", "src/conductor_host.py"]