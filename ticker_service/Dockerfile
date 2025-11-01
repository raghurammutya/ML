FROM python:3.11-slim

# Security: Run as non-root user
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies and create non-root user
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        tini \
    && useradd -m -u 1000 -s /bin/bash tickerservice \
    && chown -R tickerservice:tickerservice /app \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies as root (for permissions)
COPY --chown=tickerservice:tickerservice requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential

# Copy application code
COPY --chown=tickerservice:tickerservice . .

# Create logs directory with proper permissions
RUN mkdir -p logs tokens && \
    chown -R tickerservice:tickerservice logs tokens

# Switch to non-root user
USER tickerservice

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["python3", "start_ticker.py"]
