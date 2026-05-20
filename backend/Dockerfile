# backend/Dockerfile
# Python 3.11 slim base (Debian Bookworm) — matches the cv-module image
FROM python:3.11-slim

# ---------------------------------------------------------------------------
# Install Microsoft ODBC Driver 18 for SQL Server
# Required by aioodbc/pyodbc to connect to SQL Server from Linux.
# ACCEPT_EULA=Y is mandatory by Microsoft's licensing terms.
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        apt-transport-https \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor > /etc/apt/trusted.gpg.d/microsoft.gpg \
    && echo "deb [arch=amd64] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the API port
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
