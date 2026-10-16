# =====================================================================
# STAGE 1: COMPILATION & PACKAGING SUBSTRATE (BUILDER)
# =====================================================================
FROM python:3.13-slim AS builder

# Prevent Python from writing byte-code (.pyc) files to disk storage
ENV PYTHONDONTWRITEBYTECODE=1
# Force stdout and stderr streams to be unbuffered to avoid log loss
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install standard Linux build dependencies required for compiling binary modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency configuration into the builder context
COPY requirements.txt .

# Compile Python packages into isolated, pre-built Wheel binaries
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# =====================================================================
# STAGE 2: ARMORED RUNTIME ENVIRONMENT (FINAL TARGET)
# =====================================================================
FROM python:3.13-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Create an immutable, unprivileged system user account ring
# Assigns a fixed non-root UID/GID (1000) matching DevSecOps portfolio benchmarks
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /sbin/nologin appuser

# Extract strictly the pre-compiled native wheels from the builder stage
COPY --from=builder /app/wheels /tmp/wheels
COPY --from=builder /app/requirements.txt .

# Install packages from local binaries entirely offline, bypassing downstream supply chains
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels

# Mount our application workspace files safely into the stage tracking area
COPY --chown=appuser:appgroup orchestrator_node.py .
COPY --chown=appuser:appgroup database_manager.py .

# Enforce secure directory ownership, sealing files against runtime modifications
RUN chown -R appuser:appgroup /app

# Expose the internal service gateway port register
EXPOSE 8000

# Shed all root administrative privileges, switching execution to our non-root user
USER 1000

# Launch the orchestrator engine via Uvicorn tied strictly to unprivileged loop threads
CMD ["uvicorn", "orchestrator_node:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
