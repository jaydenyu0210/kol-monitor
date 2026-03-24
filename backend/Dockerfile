# --- Stage: Playwright base with Python 3.10 ---
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Install PostgreSQL client libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway injects PORT; default to 3001
ENV PORT=3001
EXPOSE ${PORT}

# Health check for Railway monitoring
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Start API server and scheduler concurrently
CMD ["sh", "-c", "python3 -u api_server.py & python3 -u scheduler.py"]
