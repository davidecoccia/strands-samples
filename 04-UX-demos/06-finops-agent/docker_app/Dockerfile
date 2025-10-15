# Multi-stage build for smaller final image
FROM --platform=linux/amd64 python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and wheel file first
COPY requirements.txt ./
COPY awslabs_billing_cost_management_mcp_server-0.0.2-py3-none-any.whl ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# Final stage - runtime image
FROM --platform=linux/amd64 python:3.12-slim

# Install runtime dependencies including uv
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/app/.local

# Install uv (which includes uvx) for the app user
USER app
RUN curl -LsSf https://astral.sh/uv/install.sh | sh || echo "uv installation failed, will use pip fallback"

# Set working directory and copy application
USER root
WORKDIR /app
COPY --chown=app:app . .

# Fix permissions for MCP server logs directory
RUN mkdir -p /home/app/.local/lib/python3.12/site-packages/awslabs/logs && \
    chown -R app:app /home/app/.local

# Switch to non-root user
USER app

# Make sure scripts in .local and uv are usable
ENV PATH=/home/app/.local/bin:/home/app/.cargo/bin:$PATH

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Command
CMD ["streamlit", "run", "app_streaming.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.enableCORS=false"]