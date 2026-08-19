FROM python:3.11-slim

WORKDIR /app

# Install system deps for pdfplumber and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install uv --no-cache-dir

# Copy dependency files first (layer caching)
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies
RUN uv pip install --system --no-cache ".[dev]"

# Copy source
COPY mm/ ./mm/
COPY tests/ ./tests/

# Data directory (mounted as volume in production)
RUN mkdir -p /data

ENV DATA_ROOT=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8000 8001
