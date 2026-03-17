FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install system dependencies for PostgreSQL client
RUN apt-get update && apt-get install -y libpq-dev gcc

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose API port
EXPOSE 3000

# Start script
CMD ["sh", "-c", "python3 api_server.py & python3 scheduler.py"]
