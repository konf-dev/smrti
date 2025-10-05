# Multi-stage build for Smrti API server

# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency file
COPY pyproject.toml ./

# Extract and install main dependencies using pip
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    redis==5.0.1 \
    qdrant-client==1.7.0 \
    asyncpg==0.30.0 \
    sentence-transformers==2.3.0 \
    httpx==0.26.0 \
    pydantic-settings==2.1.0 \
    structlog==24.1.0 \
    prometheus-client==0.19.0 \
    tenacity==8.2.3 \
    python-multipart==0.0.6

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 smrti && \
    mkdir -p /app/.cache && \
    chown -R smrti:smrti /app

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=smrti:smrti ./src/smrti/ /app/smrti/
COPY --chown=smrti:smrti ./pyproject.toml /app/

# Switch to non-root user
USER smrti

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "-m", "uvicorn", "smrti.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
