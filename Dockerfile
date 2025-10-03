# ==============================================================================
# SMRTI - Intelligent Multi-Tier Memory System
# Production-ready Docker image with multi-stage builds
# ==============================================================================

FROM python:3.13-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN useradd --create-home --shell /bin/bash smrti

# ==============================================================================
# DEVELOPMENT STAGE
# ==============================================================================
FROM base as development

# Install development dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    make \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e .[dev,docker]

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data/chroma && \
    chown -R smrti:smrti /app

# Switch to app user
USER smrti

# Expose ports
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["python", "-m", "smrti.api.server"]

# ==============================================================================
# PRODUCTION STAGE
# ==============================================================================
FROM base as production

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies (production only)
COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install .

# Copy only necessary application files
COPY smrti/ ./smrti/
COPY config.json ./

# Create necessary directories
RUN mkdir -p /app/logs /app/data/chroma && \
    chown -R smrti:smrti /app

# Switch to app user
USER smrti

# Expose ports
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "smrti.api.server:app"]

# ==============================================================================
# TESTING STAGE  
# ==============================================================================
FROM development as testing

# Install additional test dependencies
RUN pip install pytest-xdist pytest-mock

# Copy test files
COPY tests/ ./tests/
COPY test_*.py ./

# Run tests by default
CMD ["pytest", "-v", "--cov=smrti", "--cov-report=html", "--cov-report=term-missing"]