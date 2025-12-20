FROM python:3.13-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml .
COPY README.md .

# Create src package structure for hatch
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev

# Create downloads directory
RUN mkdir -p downloads

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["uv", "run", "uvicorn", "src.main:socket_app", "--host", "0.0.0.0", "--port", "8000"]
